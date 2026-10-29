"""Resolve a professor's scholarly identity and attach recent publications (Planning §8.3 decision 3)."""

import unicodedata
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import delete, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models import Evidence, Professor, ProfessorPublication, Publication, University
from app.services import ingestion, openalex
from app.services.openalex import AuthorCandidate

RESOLVER_VERSION = "openalex-v1"
MIN_CONFIDENCE = 0.75


@dataclass
class EnrichOutcome:
    status: str  # resolved | unresolved | duplicate
    reason: str = ""
    openalex_id: str | None = None
    confidence: float = 0.0
    publications_linked: int = 0
    duplicate_of: uuid.UUID | None = None
    candidates: list[dict] = field(default_factory=list)


def _name_key(name: str) -> tuple[str, str]:
    # ponytail: first + last token only, so middle names/initials don't block a match;
    # hyphenated or reordered names (e.g. "Zhang Wei") need a richer comparison.
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    tokens = [t for t in "".join(c if c.isalnum() else " " for c in plain).casefold().split() if len(t) > 1]
    return (tokens[0], tokens[-1]) if tokens else ("", "")


def choose_author(candidates: list[AuthorCandidate], name: str, institution_id: str | None) -> tuple[AuthorCandidate | None, float, str]:
    """Pick the author only when name AND current institution agree, and the choice is unambiguous."""
    exact = [c for c in candidates if _name_key(c.name) == _name_key(name)]
    if not exact:
        return None, 0.0, "no candidate with a matching name"
    current = [c for c in exact if institution_id and institution_id in c.current_institution_ids]
    pool = sorted(current or exact, key=lambda c: c.works_count, reverse=True)

    if len(pool) == 1:
        confidence = 0.9 if current else 0.6
    elif pool[0].works_count >= 5 * max(pool[1].works_count, 1):
        # OpenAlex often splits one person into a main profile plus small fragments.
        confidence = 0.8 if current else 0.5
    else:
        return None, 0.0, f"{len(pool)} equally plausible candidates"

    if confidence < MIN_CONFIDENCE:
        return None, confidence, "name matches but current institution does not; needs review"
    return pool[0], confidence, "name and current institution match"


def _resolve_institution(db: Session, university: University) -> str | None:
    if university.openalex_id:
        return university.openalex_id
    inst = openalex.find_institution(university.name, university.country)
    if not inst:
        return None
    inst_id = openalex.short_id(inst["id"])
    if not db.scalars(select(University).where(University.openalex_id == inst_id)).first():
        university.openalex_id = inst_id
        university.ror_id = inst.get("ror")
        university.country = inst.get("country_code")
    return inst_id


def _upsert_publication(db: Session, work: openalex.Work) -> Publication:
    keys = [Publication.openalex_id == work.openalex_id]
    if work.doi:
        keys.append(Publication.doi == work.doi)
    if work.arxiv_id:
        keys.append(Publication.arxiv_id == work.arxiv_id)
    pub = db.scalars(select(Publication).where(or_(*keys))).first()
    if pub is None:
        pub = Publication(openalex_id=work.openalex_id, title=work.title)
        db.add(pub)
    pub.doi = pub.doi or work.doi
    pub.arxiv_id = pub.arxiv_id or work.arxiv_id
    pub.title = work.title
    pub.abstract = work.abstract or pub.abstract
    pub.publication_year = work.publication_year
    pub.url = work.url
    pub.open_access_url = work.open_access_url
    db.flush()
    return pub


def enrich_professor(db: Session, professor_id: uuid.UUID, years: int = 5, limit: int = 20) -> EnrichOutcome:
    professor = db.get(Professor, professor_id)
    if professor is None:
        raise LookupError(f"professor {professor_id} not found")

    university = db.get(University, professor.university_id) if professor.university_id else None
    institution_id = _resolve_institution(db, university) if university else None

    candidates = openalex.search_authors(professor.name, institution_id, professor.orcid)
    if professor.orcid and candidates:
        chosen, confidence, reason = candidates[0], 1.0, "ORCID match"
    else:
        chosen, confidence, reason = choose_author(candidates, professor.name, institution_id)

    summary = [{"openalex_id": c.openalex_id, "name": c.name, "works_count": c.works_count,
                "current_institutions": c.current_institution_ids} for c in candidates[:5]]
    if chosen is None:
        db.commit()
        return EnrichOutcome("unresolved", reason, confidence=confidence, candidates=summary)

    other = db.scalars(select(Professor).where(
        Professor.openalex_id == chosen.openalex_id, Professor.id != professor.id,
    )).first()
    if other:
        db.commit()
        return EnrichOutcome("duplicate", "another professor record has this OpenAlex ID",
                             openalex_id=chosen.openalex_id, duplicate_of=other.id)

    professor.openalex_id = chosen.openalex_id
    professor.orcid = professor.orcid or chosen.orcid
    professor.last_verified_at = datetime.now(UTC)

    source = ingestion.save_api_record(db, chosen.api_url, chosen.raw)
    db.execute(delete(Evidence).where(
        Evidence.entity_type == "professor", Evidence.entity_id == professor.id,
        Evidence.extractor_version == RESOLVER_VERSION,
    ))
    db.add(Evidence(
        source_id=source.id, entity_type="professor", entity_id=professor.id,
        field_name="openalex_id", excerpt=f"{chosen.name}; {reason}",
        claim_value_json={"value": chosen.openalex_id, "orcid": chosen.orcid},
        verification_status="api_record", confidence=confidence, extractor_version=RESOLVER_VERSION,
    ))

    works = openalex.recent_works(chosen.openalex_id, datetime.now(UTC).year - years, limit)
    for work in works:
        pub = _upsert_publication(db, work)
        db.execute(insert(ProfessorPublication).values(
            professor_id=professor.id, publication_id=pub.id,
            author_position=work.author_position, identity_confidence=confidence,
        ).on_conflict_do_update(
            index_elements=["professor_id", "publication_id"],
            set_={"author_position": work.author_position, "identity_confidence": confidence},
        ))
    db.commit()
    return EnrichOutcome("resolved", reason, chosen.openalex_id, confidence, len(works))
