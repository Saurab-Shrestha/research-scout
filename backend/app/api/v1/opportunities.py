import uuid
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (CandidateProfile, Evidence, FundingAssessment, MatchResult, Opportunity, Professor,
                           Program, ResearchJob, University)
from app.db.session import get_db
from app.services import llm, matching

router = APIRouter(prefix="/opportunities", tags=["opportunities"])


class EvaluateRequest(BaseModel):
    professor_ids: list[uuid.UUID] | None = None  # default: every professor with a known university
    degree_types: list[Literal["phd", "thesis_masters", "course_masters"]] = ["phd", "thesis_masters"]


class OpportunityOut(BaseModel):
    id: str
    title: str
    degree_type: str
    professor_id: str
    professor: str
    faculty_url: str | None
    university: str
    country: str | None
    program: str
    program_url: str | None
    deadline: date | None
    funding_status: str
    funding_explanation: str
    stipend: str | None
    eligibility_status: str
    excluded_reason: str | None
    scores: dict[str, float]
    overall_score: float
    explanation: dict


def _stipend(f: FundingAssessment) -> str | None:
    if f.stipend_amount is None:
        return None
    return f"{f.currency or ''} {f.stipend_amount:,.0f}/{f.stipend_period or '?'}".strip()


def _rows(db: Session, opportunity_id: uuid.UUID | None = None):
    stmt = (select(Opportunity, MatchResult, Professor, Program, University, FundingAssessment)
            .join(MatchResult, MatchResult.opportunity_id == Opportunity.id)
            .join(Professor, Professor.id == Opportunity.professor_id)
            .join(Program, Program.id == Opportunity.program_id)
            .join(University, University.id == Program.university_id)
            .join(FundingAssessment, FundingAssessment.program_id == Program.id))
    if opportunity_id:
        stmt = stmt.where(Opportunity.id == opportunity_id)
    return db.execute(stmt.order_by(MatchResult.overall_score.desc())).all()


def _out(o, m, p, prog, u, f) -> OpportunityOut:
    return OpportunityOut(
        id=str(o.id), title=o.title, degree_type=o.degree_type, professor_id=str(p.id), professor=p.name,
        faculty_url=p.faculty_url, university=u.name, country=u.country, program=prog.name, program_url=prog.url,
        deadline=prog.deadline, funding_status=f.funding_status, funding_explanation=f.explanation,
        stipend=_stipend(f), eligibility_status=m.eligibility_status, excluded_reason=m.excluded_reason,
        scores={"research": m.research_score, "funding": m.funding_score, "eligibility": m.eligibility_score,
                "availability": m.availability_score, "timing": m.timing_score},
        overall_score=m.overall_score, explanation=m.explanation_json,
    )


@router.post("/evaluate", status_code=202)
def start_evaluation(body: EvaluateRequest, db: Session = Depends(get_db)):
    """Queue a background job: verify programs and funding, then score opportunities."""
    if db.scalars(select(CandidateProfile)).first() is None:
        raise HTTPException(422, "Save a candidate profile first")
    job = ResearchJob(job_type="evaluation", input_json=body.model_dump(mode="json"))
    db.add(job)
    db.commit()
    return {"job_id": str(job.id), "status": job.status}


@router.get("", response_model=list[OpportunityOut])
def list_opportunities(include_excluded: bool = False, degree_type: str | None = None, country: str | None = None,
                       min_score: float = 0, db: Session = Depends(get_db)):
    """Ranked opportunities. Excluded ones (ineligible, unfunded for you) are hidden unless requested."""
    out = [_out(*r) for r in _rows(db)]
    return [o for o in out
            if (include_excluded or o.excluded_reason is None)
            and (degree_type is None or o.degree_type == degree_type)
            and (country is None or o.country == country)
            and o.overall_score >= min_score]


@router.get("/{opportunity_id}")
def get_opportunity(opportunity_id: uuid.UUID, db: Session = Depends(get_db)):
    rows = _rows(db, opportunity_id)
    if not rows:
        raise HTTPException(404, "Opportunity not found or not scored yet")
    opp = _out(*rows[0])
    program = rows[0][3]
    evidence = db.scalars(select(Evidence).where(Evidence.entity_type == "program", Evidence.entity_id == program.id)
                          .order_by(Evidence.field_name)).all()
    return {**opp.model_dump(mode="json"), "requirements": program.requirements_json,
            "program_evidence": [{"field": e.field_name, "value": (e.claim_value_json or {}).get("value"),
                                  "quote": e.excerpt, "status": e.verification_status, "source_id": str(e.source_id)}
                                 for e in evidence]}


@router.post("/{opportunity_id}/evaluate", response_model=OpportunityOut)
def rescore(opportunity_id: uuid.UUID, db: Session = Depends(get_db)):
    """Recompute eligibility and score from stored evidence (no page re-fetching)."""
    opportunity = db.get(Opportunity, opportunity_id)
    profile = db.scalars(select(CandidateProfile)).first()
    if opportunity is None or profile is None:
        raise HTTPException(404, "Opportunity or profile not found")
    try:
        matching.score_opportunity(db, profile, opportunity)
    except llm.LLMError as e:
        raise HTTPException(502, str(e))
    return _out(*_rows(db, opportunity_id)[0])
