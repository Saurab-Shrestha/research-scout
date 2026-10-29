import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Evidence, Professor
from app.db.session import get_db

router = APIRouter(prefix="/professors", tags=["professors"])


class EvidenceOut(BaseModel):
    id: str
    source_id: str
    field_name: str
    value: str | None
    excerpt: str
    verification_status: str


class ProfessorOut(BaseModel):
    id: str
    name: str
    title: str | None
    email: str | None
    faculty_url: str | None
    research_summary: str | None
    accepting_students: bool | None
    university_id: str | None
    department_id: str | None
    evidence: list[EvidenceOut] = []


def _to_out(p: Professor, evidence: list[Evidence] = ()) -> ProfessorOut:
    return ProfessorOut(
        id=str(p.id), name=p.name, title=p.title, email=p.email, faculty_url=p.faculty_url,
        research_summary=p.research_summary, accepting_students=p.accepting_students,
        university_id=str(p.university_id) if p.university_id else None,
        department_id=str(p.department_id) if p.department_id else None,
        evidence=[EvidenceOut(
            id=str(e.id), source_id=str(e.source_id), field_name=e.field_name,
            value=(e.claim_value_json or {}).get("value"), excerpt=e.excerpt,
            verification_status=e.verification_status,
        ) for e in evidence],
    )


@router.get("", response_model=list[ProfessorOut])
def list_professors(q: str | None = None, limit: int = 50, db: Session = Depends(get_db)):
    stmt = select(Professor).order_by(Professor.name).limit(min(limit, 200))
    if q:
        stmt = stmt.where(Professor.name.ilike(f"%{q}%"))
    return [_to_out(p) for p in db.scalars(stmt)]


@router.get("/{professor_id}", response_model=ProfessorOut)
def get_professor(professor_id: uuid.UUID, db: Session = Depends(get_db)):
    professor = db.get(Professor, professor_id)
    if professor is None:
        raise HTTPException(404, "Professor not found")
    evidence = db.scalars(select(Evidence).where(
        Evidence.entity_type == "professor", Evidence.entity_id == professor_id,
    ).order_by(Evidence.field_name)).all()
    return _to_out(professor, evidence)
