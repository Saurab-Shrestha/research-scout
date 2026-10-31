"""Outreach email and SOP outline drafts, grounded in stored papers and program facts (Planning F6)."""

import json
import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (Application, CandidateProfile, Department, Draft, FundingAssessment, MatchResult, Opportunity, Professor,
                           ProfessorPublication, Program, Publication, University)
from app.prompts import drafts as prompt
from app.schemas.drafts import EmailDraft, SopOutline
from app.services import llm

MAX_PAPERS = 5
MAX_EMAIL_WORDS = 180
MAX_FOLLOW_UP_WORDS = 100


class DraftError(ValueError):
    """The draft can't be written from what is stored yet; the message says what to do first."""


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


def _follow_up_context(db: Session, opportunity: Opportunity, today: date) -> tuple[str, Draft, list[str]]:
    """The first email (latest saved version) and when it went out; a follow-up only makes sense after both."""
    first = db.scalars(select(Draft).where(Draft.opportunity_id == opportunity.id, Draft.kind == "email")
                       .order_by(Draft.created_at.desc())).first()
    if first is None:
        raise DraftError("Write the first email before a follow-up.")
    app = db.scalars(select(Application).where(Application.opportunity_id == opportunity.id)).first()
    sent = app.contacted_at if app else None
    warnings = []
    if sent is None:
        warnings.append("This professor isn't marked as contacted. Mark the first email as sent before following up.")
    elif (today - sent).days < 7:
        warnings.append(f"Only {(today - sent).days} days since your first email; most replies take one to two weeks.")
    section = {"subject": first.subject, "body": first.body, "sent_on": sent.isoformat() if sent else None,
               "days_without_reply": (today - sent).days if sent else None}
    return f"FIRST_EMAIL:\n{json.dumps(section, ensure_ascii=False)}", first, warnings


def generate_draft(db: Session, opportunity: Opportunity, profile: CandidateProfile, kind: str,
                   today: date | None = None) -> Draft:
    context, papers, trace = build_context(db, opportunity, profile)
    warnings: list[str] = []
    if kind == "email":
        result = llm.generate_structured(prompt.EMAIL_SYSTEM, context, EmailDraft)
        subject, body = result.parsed.subject, result.parsed.body
    elif kind == "follow_up":
        extra, first, warnings = _follow_up_context(db, opportunity, today or date.today())
        context += "\n\n" + extra
        trace = {**trace, "first_email_id": str(first.id), "context": context}
        result = llm.generate_structured(prompt.FOLLOW_UP_SYSTEM, context, EmailDraft)
        # Same thread: the subject is the first email's, never the model's.
        subject = first.subject if (first.subject or "").lower().startswith("re:") else f"Re: {first.subject or ''}".strip()
        body = result.parsed.body
    else:
        result = llm.generate_structured(prompt.SOP_SYSTEM, context, SopOutline)
        subject, body = None, _sop_markdown(result.parsed)
    ids, citation_warnings = _check_citations(result.parsed.cited_papers, papers)
    warnings += citation_warnings
    limit = {"email": MAX_EMAIL_WORDS, "follow_up": MAX_FOLLOW_UP_WORDS}.get(kind)
    if limit and len(body.split()) > limit + 20:
        warnings.append(f"Body is {len(body.split())} words; aim for under {limit}.")
    if "[" in body:
        warnings.append("Fill in the bracketed placeholders before sending.")
    if not papers:
        warnings.append("No stored publications for this professor; refresh publications for a specific email.")
    draft = Draft(opportunity_id=opportunity.id, kind=kind, subject=subject, body=body, cited_publication_ids=ids,
                  warnings=warnings, model=result.model, prompt_version=prompt.VERSION, context_json=trace)
    db.add(draft)
    db.commit()
    return draft
