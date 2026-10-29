import uuid
from datetime import UTC, date, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Application, CandidateProfile, Opportunity, Professor, Program, University
from app.db.session import get_db
from app.services.tracker import STATUSES, suggest_next_action

router = APIRouter(prefix="/applications", tags=["applications"])
Status = Literal[tuple(STATUSES)]


class ApplicationCreate(BaseModel):
    opportunity_id: uuid.UUID
    notes: str = ""


class ApplicationUpdate(BaseModel):
    status: Status | None = None
    contacted_at: date | None = None
    deadline: date | None = None
    next_action: str | None = None
    next_action_at: date | None = None
    notes: str | None = None


class ApplicationOut(BaseModel):
    id: str
    opportunity_id: str
    title: str
    professor: str
    professor_email: str | None
    university: str
    country: str | None
    degree_type: str
    status: str
    contacted_at: date | None
    deadline: date | None
    next_action: str | None
    next_action_at: date | None
    notes: str
    history: list[dict]


def _out(db: Session, a: Application) -> ApplicationOut:
    opp = db.get(Opportunity, a.opportunity_id)
    prof = db.get(Professor, opp.professor_id)
    uni = db.get(University, db.get(Program, opp.program_id).university_id)
    return ApplicationOut(
        id=str(a.id), opportunity_id=str(opp.id), title=opp.title, professor=prof.name, professor_email=prof.email,
        university=uni.name, country=uni.country, degree_type=opp.degree_type, status=a.status,
        contacted_at=a.contacted_at, deadline=a.deadline, next_action=a.next_action,
        next_action_at=a.next_action_at, notes=a.notes, history=a.history_json,
    )


def _refresh_suggestion(db: Session, a: Application) -> None:
    opp = db.get(Opportunity, a.opportunity_id)
    country = db.get(University, db.get(Program, opp.program_id).university_id).country
    a.next_action, a.next_action_at = suggest_next_action(country, opp.degree_type, a.status, a.deadline,
                                                          datetime.now(UTC).date())


@router.post("", response_model=ApplicationOut, status_code=201)
def create_application(body: ApplicationCreate, db: Session = Depends(get_db)):
    opp = db.get(Opportunity, body.opportunity_id)
    profile = db.scalars(select(CandidateProfile)).first()
    if opp is None or profile is None:
        raise HTTPException(404, "Opportunity or profile not found")
    existing = db.scalars(select(Application).where(Application.opportunity_id == opp.id)).first()
    if existing:
        return _out(db, existing)  # idempotent: saving twice returns the same tracker entry
    a = Application(opportunity_id=opp.id, candidate_profile_id=profile.id, notes=body.notes, status="shortlisted",
                    deadline=db.get(Program, opp.program_id).deadline,
                    history_json=[{"at": datetime.now(UTC).isoformat(), "status": "shortlisted"}])
    _refresh_suggestion(db, a)
    db.add(a)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        a = db.scalars(select(Application).where(Application.opportunity_id == opp.id)).one()
    return _out(db, a)


@router.get("", response_model=list[ApplicationOut])
def list_applications(include_closed: bool = True, db: Session = Depends(get_db)):
    rows = db.scalars(select(Application).order_by(Application.next_action_at.asc().nulls_last(),
                                                   Application.created_at)).all()
    out = [_out(db, a) for a in rows]
    return out if include_closed else [a for a in out if a.status not in ("offer", "rejected", "declined", "withdrawn")]


@router.patch("/{application_id}", response_model=ApplicationOut)
def update_application(application_id: uuid.UUID, body: ApplicationUpdate, db: Session = Depends(get_db)):
    a = db.get(Application, application_id)
    if a is None:
        raise HTTPException(404, "Application not found")
    changes = body.model_dump(exclude_unset=True)
    status_changed = "status" in changes and changes["status"] != a.status
    for key, value in changes.items():
        setattr(a, key, value)
    if status_changed:
        if a.status == "contacted" and a.contacted_at is None:
            a.contacted_at = datetime.now(UTC).date()
        a.history_json = [*a.history_json, {"at": datetime.now(UTC).isoformat(), "status": a.status}]
        if "next_action" not in changes:
            _refresh_suggestion(db, a)
    db.commit()
    return _out(db, a)


@router.delete("/{application_id}", status_code=204)
def delete_application(application_id: uuid.UUID, db: Session = Depends(get_db)):
    a = db.get(Application, application_id)
    if a is None:
        raise HTTPException(404, "Application not found")
    db.delete(a)
    db.commit()
