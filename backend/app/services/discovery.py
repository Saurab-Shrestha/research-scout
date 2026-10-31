"""Scholarly-graph-first discovery (Planning §3.1): turn OpenAlex authors into professor records."""

import uuid
from collections import Counter
from dataclasses import dataclass

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Professor, University
from app.prompts import topic_planner
from app.services import llm, openalex, publications

AREA_QUERIES = {
    "machine_learning": ["machine learning", "deep learning"],
    "artificial_intelligence": ["artificial intelligence"],
    "quantum_computing": ["quantum computing", "quantum information"],
}

# ponytail: crude seniority heuristic to skip students/postdocs; replace with faculty-page
# verification (title extraction) once page discovery runs in the pipeline.
MIN_WORKS = 25
MIN_H_INDEX = 10


@dataclass
class Candidate:
    author_id: str
    name: str
    orcid: str | None
    topic_works: int
    institution: dict | None  # OpenAlex institution object
    affiliation_note: str
    raw: dict


def topic_queries(research_areas: list[str], query: str | None) -> list[str]:
    queries = [q for area in research_areas for q in AREA_QUERIES.get(area, [area.replace("_", " ")])]
    if query and query.strip():
        queries.append(query.strip())
    return list(dict.fromkeys(queries))


def primary_institution(author: dict, countries: list[str], current_year: int) -> tuple[dict | None, str]:
    """Pick the university with the most recent affiliation years; refuse to guess on ties.

    OpenAlex affiliation lists mix old, visiting and merged-profile entries, so this only
    trusts universities seen in the last three years.
    """
    recent = Counter()
    institutions = {}
    for aff in author.get("affiliations") or []:
        inst = aff["institution"]
        if inst.get("type") != "education" or inst.get("country_code") not in countries:
            continue
        hits = sum(1 for y in aff.get("years", []) if y >= current_year - 2)
        if hits:
            recent[inst["id"]] += hits
            institutions[inst["id"]] = inst
    if not recent:
        return None, "no recent university affiliation in target countries"
    ranked = recent.most_common(2)
    if len(ranked) == 2 and ranked[0][1] == ranked[1][1]:
        names = " / ".join(institutions[i]["display_name"] for i, _ in ranked)
        return None, f"ambiguous current affiliation: {names}"
    best = ranked[0][0]
    # Co-authorship noise can attach a university to someone based elsewhere; require
    # OpenAlex's own last-known list to agree when it exists.
    last_known = {i["id"] for i in author.get("last_known_institutions") or []}
    if last_known and best not in last_known:
        return None, f"{institutions[best]['display_name']} not among last known institutions"
    return institutions[best], "most recent university affiliation"


def looks_senior(author: dict) -> bool:
    h_index = (author.get("summary_stats") or {}).get("h_index") or 0
    return author.get("works_count", 0) >= MIN_WORKS and h_index >= MIN_H_INDEX


def known_keys(db: Session) -> set:
    """OpenAlex IDs plus (name, university) pairs of professors already saved.

    The name pair catches OpenAlex split profiles: one person under two author IDs.
    """
    rows = db.execute(select(Professor.openalex_id, Professor.name, University.openalex_id)
                      .outerjoin(University, Professor.university_id == University.id))
    keys = set()
    for author_id, name, inst_id in rows:
        keys.add(author_id)
        if inst_id:
            keys.add((publications._name_key(name), inst_id))
    keys.discard(None)
    return keys


def select_candidates(authors: list[dict], topic_counts: dict[str, int], countries: list[str],
                      current_year: int, max_results: int, known: set = frozenset()) -> tuple[list[Candidate], list[dict]]:
    """`known` (from known_keys) skips researchers already saved, so max_results counts only new ones."""
    kept, skipped = [], []
    for a in authors:
        author_id = openalex.short_id(a["id"])
        if author_id in known:
            skipped.append({"name": a["display_name"], "reason": "already in your list"})
            continue
        if not looks_senior(a):
            skipped.append({"name": a["display_name"], "reason": "below seniority threshold"})
            continue
        inst, note = primary_institution(a, countries, current_year)
        if inst is None:
            skipped.append({"name": a["display_name"], "reason": note})
            continue
        if (publications._name_key(a["display_name"]), openalex.short_id(inst["id"])) in known:
            skipped.append({"name": a["display_name"], "reason": "already in your list (another OpenAlex profile)"})
            continue
        kept.append(Candidate(
            author_id=author_id,
            name=a["display_name"],
            orcid=(a.get("orcid") or "").removeprefix("https://orcid.org/").lower() or None,
            topic_works=topic_counts.get(author_id, 0),
            institution=inst,
            affiliation_note=note,
            raw=a,
        ))
    kept.sort(key=lambda c: c.topic_works, reverse=True)
    return kept[:max_results], skipped


def upsert_candidate(db: Session, c: Candidate) -> tuple[uuid.UUID, bool]:
    """Create or update the professor for an OpenAlex author. Returns (professor_id, created)."""
    inst_id = openalex.short_id(c.institution["id"])
    university = db.scalars(select(University).where(University.openalex_id == inst_id)).first()
    if university is None:
        name = c.institution["display_name"]
        university = University(
            name=name, normalized_name=name.casefold().removeprefix("the "),
            country=c.institution.get("country_code"), openalex_id=inst_id, ror_id=c.institution.get("ror"),
        )
        db.add(university)
        db.flush()

    professor = db.scalars(select(Professor).where(Professor.openalex_id == c.author_id)).first()
    created = professor is None
    if created:
        professor = Professor(name=c.name, openalex_id=c.author_id, orcid=c.orcid, university_id=university.id)
        db.add(professor)
        db.flush()
    elif professor.university_id is None:
        professor.university_id = university.id

    confidence = 0.7  # OpenAlex-only identity; raised when a faculty page confirms it
    publications.record_identity_evidence(
        db, professor.id, f"{openalex.BASE}/authors/{c.author_id}", c.raw,
        f"{c.name}; {c.affiliation_note}: {c.institution['display_name']}",
        c.author_id, c.orcid, confidence,
    )
    db.commit()
    return professor.id, created


class SelectedTopic(BaseModel):
    topic_id: str
    reason: str


class TopicSelection(BaseModel):
    selected: list[SelectedTopic]


def choose_topics(research_areas: list[str], query: str | None, candidates_per_query: dict[str, list[dict]]) -> tuple[list[dict], str]:
    """Let Gemini pick relevant topics from OpenAlex candidates; fall back to best match per query."""
    candidates = {c["id"]: c for cs in candidates_per_query.values() for c in cs}
    fallback = list({cs[0]["id"]: cs[0] for cs in candidates_per_query.values() if cs}.values())
    if len(candidates) <= 1:
        return fallback, "single candidate"
    try:
        result = llm.generate_structured(
            topic_planner.SYSTEM,
            topic_planner.build_user_message(research_areas, query, list(candidates.values())),
            TopicSelection,
            settings.extraction_model,
        )
    except llm.LLMError as e:
        return fallback, f"fallback (planner failed: {e})"
    chosen = [candidates[t.topic_id] | {"reason": t.reason}
              for t in result.parsed.selected if t.topic_id in candidates]  # ignore invented IDs
    chosen = list({c["id"]: c for c in chosen}.values())[:6]
    return (chosen, topic_planner.VERSION) if chosen else (fallback, "fallback (planner chose nothing)")
