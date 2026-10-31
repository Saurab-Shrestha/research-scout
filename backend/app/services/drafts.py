"""Outreach email and SOP outline drafts, grounded in stored papers and program facts (Planning F6)."""

import json
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import (CandidateProfile, Department, Draft, FundingAssessment, MatchResult, Opportunity, Professor,
                           ProfessorPublication, Program, Publication, University)
from app.prompts import drafts as prompt
from app.schemas.drafts import EmailDraft, SopOutline
from app.services import llm

MAX_PAPERS = 5
MAX_EMAIL_WORDS = 180


def _papers(db: Session, opportunity: Opportunity) -> list[Publication]:
    """Best research matches first, then the professor's most recent papers."""
    match = db.scalars(select(MatchResult).where(MatchResult.opportunity_id == opportunity.id)).first()
    ids = [uuid.UUID(m["publication_id"]) for m in (match.explanation_json if match else {}).get("research_matches", [])]
    recent = db.scalars(select(Publication.id).join(ProfessorPublication)
                        .where(ProfessorPublication.professor_id == opportunity.professor_id)
                        .order_by(Publication.publication_year.desc().nulls_last()).limit(MAX_PAPERS)).all()
    ordered = list(dict.fromkeys(ids + list(recent)))[:MAX_PAPERS]
    return [db.get(Publication, i) for i in ordered]


def build_context(db: Session, opportunity: Opportunity, profile: CandidateProfile) -> tuple[str, list[Publication], dict]:
    professor = db.get(Professor, opportunity.professor_id)
    program = db.get(Program, opportunity.program_id)
    university = db.get(University, program.university_id)
    department = db.get(Department, professor.department_id) if professor.department_id else None
    funding = db.scalars(select(FundingAssessment).where(FundingAssessment.program_id == program.id)).first()
    papers = _papers(db, opportunity)
    sections = {
        "CANDIDATE": {"name": profile.name, "education": profile.education_json, "experience": profile.experience_json,
                      "skills": profile.skills_json, "research_interests": profile.research_interests,
                      "career_goals": profile.career_goals, "intended_start_term": profile.intended_start_term},
        "PROFESSOR": {"name": professor.name, "title": professor.title, "university": university.name,
                      "department": department.name if department else None, "faculty_url": professor.faculty_url},
        "PAPERS": [{"title": p.title, "year": p.publication_year, "abstract": (p.abstract or "")[:800]} for p in papers],
        "PROGRAM": {"name": program.name, "degree_type": opportunity.degree_type, "country": university.country,
                    "deadline": program.deadline.isoformat() if program.deadline else None,
                    "supervisor_required_before_admission": (program.requirements_json or {}).get("supervisor_required"),
                    "funding_status": funding.funding_status if funding else None},
    }
    text = "\n\n".join(f"{k}:\n{json.dumps(v, ensure_ascii=False, default=str)}" for k, v in sections.items())
    trace = {"profile_id": str(profile.id), "profile_updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
             "professor_id": str(professor.id), "publication_ids": [str(p.id) for p in papers],
             "program_id": str(program.id), "program_source_ids": program.source_ids or [],
             "funding_evidence_ids": (funding.evidence_ids or []) if funding else [], "context": text}
    return text, papers, trace


def _check_citations(cited: list[str], papers: list[Publication]) -> tuple[list[str], list[str]]:
    by_title = {p.title.strip().lower(): str(p.id) for p in papers}
    ids, warnings = [], []
    for title in cited:
        pid = by_title.get(title.strip().lower())
        if pid:
            ids.append(pid)
        else:
            warnings.append(f"Cites a paper not in the professor's stored publications: {title!r}. Check or remove it.")
    return ids, warnings


def _sop_markdown(outline: SopOutline) -> str:
    return "\n\n".join(f"## {s.heading}\n" + "\n".join(f"- {p}" for p in s.points) for s in outline.sections)


def generate_draft(db: Session, opportunity: Opportunity, profile: CandidateProfile, kind: str) -> Draft:
    context, papers, trace = build_context(db, opportunity, profile)
    if kind == "email":
        result = llm.generate_structured(prompt.EMAIL_SYSTEM, context, EmailDraft, settings.extraction_model)
        subject, body = result.parsed.subject, result.parsed.body
    else:
        result = llm.generate_structured(prompt.SOP_SYSTEM, context, SopOutline, settings.extraction_model)
        subject, body = None, _sop_markdown(result.parsed)
    ids, warnings = _check_citations(result.parsed.cited_papers, papers)
    if kind == "email" and len(body.split()) > MAX_EMAIL_WORDS + 20:
        warnings.append(f"Body is {len(body.split())} words; aim for under {MAX_EMAIL_WORDS}.")
    if "[" in body:
        warnings.append("Fill in the bracketed placeholders before sending.")
    if not papers:
        warnings.append("No stored publications for this professor; refresh publications for a specific email.")
    draft = Draft(opportunity_id=opportunity.id, kind=kind, subject=subject, body=body, cited_publication_ids=ids,
                  warnings=warnings, model=result.model, prompt_version=prompt.VERSION, context_json=trace)
    db.add(draft)
    db.commit()
    return draft
