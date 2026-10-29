"""Research alignment and deterministic opportunity scoring (Planning §12.2)."""

import math
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (CandidateProfile, FundingAssessment, MatchResult, Opportunity, Professor,
                           ProfessorPublication, Program, Publication, University)
from app.services import eligibility, llm

SCORING_VERSION = "score-v1"
WEIGHTS = {"research": 0.35, "funding": 0.25, "eligibility": 0.20, "availability": 0.10, "timing": 0.10}
FUNDING_POINTS = {"confirmed_full": 100, "confirmed_partial": 70, "advertised_unverified": 50,
                  "potential": 35, "unknown": 20, "unfunded": 0}
ELIGIBILITY_POINTS = {"eligible": 100, "potentially_eligible": 60, "insufficient_information": 40, "ineligible": 0}
# Calibration knobs: cosine similarity of gemini-embedding-001 vectors mapped linearly to 0-100.
# Measured on real data (Oct 2026): loosely related work scores ~0.80-0.82, strong matches 0.85-0.89.
SIM_FLOOR, SIM_CEIL = 0.78, 0.90


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    return dot / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)) or 1.0)


def ensure_embeddings(db: Session, profile: CandidateProfile, publications: list[Publication]) -> None:
    cached = profile.interest_embeddings or {}
    missing = [i for i in profile.research_interests if i not in cached]
    if missing:
        profile.interest_embeddings = cached | dict(zip(missing, llm.embed(missing)))
    todo = [p for p in publications if p.embedding is None]
    if todo:
        for pub, vec in zip(todo, llm.embed([f"{p.title}. {(p.abstract or '')[:1500]}" for p in todo])):
            pub.embedding = vec
    db.commit()


def research_alignment(profile: CandidateProfile, publications: list[Publication]) -> tuple[float, list[dict]]:
    """Score from the best-matching interest (80%) plus the runner-up (20%), so a specialist who strongly
    matches one of several interests is not penalised. Returns the top matches as the explanation."""
    if not publications or not profile.interest_embeddings:
        return 0.0, []
    matches = []
    for interest in profile.research_interests:
        vec = profile.interest_embeddings.get(interest)
        if vec is None:
            continue
        best = max(publications, key=lambda p: _cosine(vec, p.embedding))
        matches.append({"interest": interest, "similarity": round(_cosine(vec, best.embedding), 3),
                        "paper": best.title, "year": best.publication_year, "publication_id": str(best.id)})
    matches.sort(key=lambda m: m["similarity"], reverse=True)
    top = [m["similarity"] for m in matches[:2]]
    raw = 0.8 * top[0] + 0.2 * top[-1] if top else 0.0
    return round(max(0.0, min(100.0, (raw - SIM_FLOOR) / (SIM_CEIL - SIM_FLOOR) * 100)), 1), matches[:3]


def availability_score(professor: Professor, last_author_recent: int) -> float:
    base = {True: 100, False: 10, None: 50}[professor.accepting_students]
    return min(100.0, base + (20 if professor.accepting_students is None and last_author_recent >= 2 else 0))


def timing_score(deadline: date | None, today: date) -> float:
    if deadline is None:
        return 50.0
    days = (deadline - today).days
    return 0.0 if days < 0 else 30.0 if days < 14 else 60.0 if days < 45 else 100.0


def overall(components: dict[str, float]) -> float:
    return round(sum(WEIGHTS[k] * v for k, v in components.items()), 1)


def exclusion_reason(eligibility_status: str, funding: FundingAssessment, prefs: dict) -> str | None:
    if eligibility_status == "ineligible":
        return "ineligible"
    if funding.international_eligible is False:
        return "funding not available to international students"
    if funding.funding_status == "unfunded" and (prefs.get("needs_tuition_coverage") or prefs.get("needs_living_stipend")):
        return "unfunded"
    if prefs.get("requires_funding_at_admission") and funding.timing == "after_enrollment":
        return "funding only after enrollment"
    return None


def score_opportunity(db: Session, profile: CandidateProfile, opportunity: Opportunity, today: date | None = None) -> MatchResult:
    today = today or datetime.now(UTC).date()
    professor = db.get(Professor, opportunity.professor_id)
    program = db.get(Program, opportunity.program_id)
    university = db.get(University, program.university_id)
    funding = db.scalars(select(FundingAssessment).where(FundingAssessment.program_id == program.id)).one()
    rows = db.execute(select(Publication, ProfessorPublication.author_position)
                      .join(ProfessorPublication, ProfessorPublication.publication_id == Publication.id)
                      .where(ProfessorPublication.professor_id == professor.id)).all()
    pubs = [p for p, _ in rows if p.embedding is not None]
    last_author_recent = sum(1 for p, pos in rows if pos == "last" and (p.publication_year or 0) >= today.year - 2)

    profile_data = {"education": profile.education_json, "test_scores": profile.test_scores_json}
    elig_status, checks = eligibility.evaluate(profile_data, program.requirements_json, university.country,
                                               program.degree_type, program.deadline, today)
    research, matches = research_alignment(profile, pubs)
    components = {
        "research": research,
        "funding": float(FUNDING_POINTS[funding.funding_status]),
        "eligibility": float(ELIGIBILITY_POINTS[elig_status]),
        "availability": availability_score(professor, last_author_recent),
        "timing": timing_score(program.deadline, today),
    }
    result = db.scalars(select(MatchResult).where(MatchResult.candidate_profile_id == profile.id,
                                                  MatchResult.opportunity_id == opportunity.id)).first()
    if result is None:
        result = MatchResult(candidate_profile_id=profile.id, opportunity_id=opportunity.id)
        db.add(result)
    result.research_score = components["research"]
    result.funding_score = components["funding"]
    result.eligibility_score = components["eligibility"]
    result.availability_score = components["availability"]
    result.timing_score = components["timing"]
    result.overall_score = overall(components)
    result.eligibility_status = elig_status
    result.funding_status = funding.funding_status
    result.excluded_reason = exclusion_reason(elig_status, funding, profile.funding_preferences_json)
    result.explanation_json = {
        "research_matches": matches, "eligibility_checks": checks, "funding": funding.explanation,
        "weights": WEIGHTS, "last_author_papers_recent": last_author_recent,
    }
    result.scoring_version = SCORING_VERSION
    db.commit()
    return result
