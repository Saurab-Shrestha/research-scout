import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Evidence, Professor, ProfessorPublication, Publication, Source, University
from app.db.session import get_db
from app.services import page_finder, publications
from app.services.llm import LLMError
from app.services.openalex import ScholarlyError

router = APIRouter(prefix="/professors", tags=["professors"])


class EvidenceOut(BaseModel):
    id: str
    source_id: str
    field_name: str
    value: str | None
    excerpt: str
    verification_status: str
    source_url: str | None = None
    checked_at: datetime | None = None


class PublicationOut(BaseModel):
    id: str
    title: str
    publication_year: int | None
    doi: str | None
    arxiv_id: str | None
    url: str | None
    open_access_url: str | None
    abstract: str | None
    author_position: str | None


class ProfessorOut(BaseModel):
    id: str
    name: str
    title: str | None
    email: str | None
    faculty_url: str | None
    research_summary: str | None
    openalex_id: str | None
    orcid: str | None
    accepting_students: bool | None
    university_id: str | None
    university: str | None = None
    country: str | None = None
    department_id: str | None
    # Directory-only summary of publication activity; detail responses carry the full list instead.
    publication_count: int | None = None
    latest_publication_year: int | None = None
    evidence: list[EvidenceOut] = []
    publications: list[PublicationOut] = []


def _to_out(p: Professor, university: str | None = None,
            evidence: list[tuple[Evidence, str | None, datetime | None]] = (),
            pubs: list[tuple[Publication, str | None]] = ()) -> ProfessorOut:
    return ProfessorOut(
        id=str(p.id), name=p.name, title=p.title, email=p.email, faculty_url=p.faculty_url,
        research_summary=p.research_summary, openalex_id=p.openalex_id, orcid=p.orcid,
        accepting_students=p.accepting_students,
        university_id=str(p.university_id) if p.university_id else None, university=university,
        department_id=str(p.department_id) if p.department_id else None,
        evidence=[EvidenceOut(
            id=str(e.id), source_id=str(e.source_id), field_name=e.field_name,
            value=(e.claim_value_json or {}).get("value"), excerpt=e.excerpt,
            verification_status=e.verification_status, source_url=url, checked_at=fetched,
        ) for e, url, fetched in evidence],
        publications=[PublicationOut(
            id=str(pub.id), title=pub.title, publication_year=pub.publication_year, doi=pub.doi,
            arxiv_id=pub.arxiv_id, url=pub.url, open_access_url=pub.open_access_url,
            abstract=pub.abstract, author_position=position,
        ) for pub, position in pubs],
    )


@router.get("", response_model=list[ProfessorOut])
def list_professors(q: str | None = None, ids: list[uuid.UUID] | None = Query(None), limit: int = 50,
                    db: Session = Depends(get_db)):
    activity = (select(ProfessorPublication.professor_id, func.count().label("n"),
                       func.max(Publication.publication_year).label("latest"))
                .join(Publication, Publication.id == ProfessorPublication.publication_id)
                .group_by(ProfessorPublication.professor_id).subquery())
    stmt = (select(Professor, University.name, University.country, activity.c.n, activity.c.latest)
            .outerjoin(University, University.id == Professor.university_id)
            .outerjoin(activity, activity.c.professor_id == Professor.id)
            .order_by(Professor.name).limit(min(limit, 200)))
    if q:
        stmt = stmt.where(Professor.name.ilike(f"%{q}%"))
    if ids:
        stmt = stmt.where(Professor.id.in_(ids))
    return [_to_out(p, uni).model_copy(update={"country": country, "publication_count": n or 0, "latest_publication_year": latest})
            for p, uni, country, n, latest in db.execute(stmt)]


@router.get("/{professor_id}", response_model=ProfessorOut)
def get_professor(professor_id: uuid.UUID, db: Session = Depends(get_db)):
    professor = db.get(Professor, professor_id)
    if professor is None:
        raise HTTPException(404, "Professor not found")
    evidence = db.execute(select(Evidence, Source.url, Source.fetched_at).join(Source, Source.id == Evidence.source_id).where(
        Evidence.entity_type == "professor", Evidence.entity_id == professor_id,
    ).order_by(Evidence.field_name)).all()
    pubs = db.execute(
        select(Publication, ProfessorPublication.author_position)
        .join(ProfessorPublication, ProfessorPublication.publication_id == Publication.id)
        .where(ProfessorPublication.professor_id == professor_id)
        .order_by(Publication.publication_year.desc().nulls_last(), Publication.title)
    ).all()
    university = db.get(University, professor.university_id) if professor.university_id else None
    return _to_out(professor, university.name if university else None, evidence, pubs)


@router.post("/{professor_id}/refresh")
def refresh_professor(professor_id: uuid.UUID, db: Session = Depends(get_db)):
    """Resolve the professor's OpenAlex identity and pull recent publications."""
    try:
        outcome = publications.enrich_professor(db, professor_id)
    except LookupError:
        raise HTTPException(404, "Professor not found")
    except ScholarlyError as e:
        raise HTTPException(502, str(e))
    return {
        "status": outcome.status,
        "reason": outcome.reason,
        "openalex_id": outcome.openalex_id,
        "confidence": outcome.confidence,
        "publications_linked": outcome.publications_linked,
        "duplicate_of": str(outcome.duplicate_of) if outcome.duplicate_of else None,
        "candidates": outcome.candidates,
    }


@router.post("/{professor_id}/find-page")
def find_page(professor_id: uuid.UUID, db: Session = Depends(get_db)):
    """Search for the professor's official page and attach it only if extraction confirms identity."""
    try:
        outcome = page_finder.find_faculty_page(db, professor_id)
    except LookupError:
        raise HTTPException(404, "Professor not found")
    except LLMError as e:
        raise HTTPException(502, str(e))
    return {"status": outcome.status, "faculty_url": outcome.faculty_url, "attempts": outcome.attempts,
            "search_queries": outcome.search_queries, "answer": outcome.answer}
