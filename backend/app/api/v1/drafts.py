import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import CandidateProfile, Draft, Opportunity
from app.db.session import get_db
from app.services import drafts, llm

router = APIRouter(tags=["drafts"])


class DraftCreate(BaseModel):
    kind: Literal["email", "follow_up", "sop_outline"]


class DraftUpdate(BaseModel):
    subject: str | None = None
    body: str | None = None


class DraftOut(BaseModel):
    id: str
    opportunity_id: str
    kind: str
    subject: str | None
    body: str
    cited_publication_ids: list[str]
    warnings: list[str]
    model: str
    prompt_version: str
    sources: dict  # what the draft was built from (IDs only; the full context text is in the database)
    created_at: datetime


def _out(d: Draft) -> DraftOut:
    return DraftOut(id=str(d.id), opportunity_id=str(d.opportunity_id), kind=d.kind, subject=d.subject, body=d.body,
                    cited_publication_ids=d.cited_publication_ids, warnings=d.warnings, model=d.model,
                    prompt_version=d.prompt_version,
                    sources={k: v for k, v in (d.context_json or {}).items() if k != "context"}, created_at=d.created_at)


@router.post("/opportunities/{opportunity_id}/drafts", response_model=DraftOut, status_code=201)
def create_draft(opportunity_id: uuid.UUID, body: DraftCreate, db: Session = Depends(get_db)):
    """Generate a new draft (~10 s). Never sends anything; the candidate edits and sends it themselves."""
    opportunity = db.get(Opportunity, opportunity_id)
    profile = db.scalars(select(CandidateProfile)).first()
    if opportunity is None or profile is None:
        raise HTTPException(404, "Opportunity or profile not found")
    try:
        return _out(drafts.generate_draft(db, opportunity, profile, body.kind))
    except drafts.DraftError as e:
        raise HTTPException(422, str(e))
    except llm.LLMError as e:
        raise HTTPException(502, str(e))


@router.get("/opportunities/{opportunity_id}/drafts", response_model=list[DraftOut])
def list_drafts(opportunity_id: uuid.UUID, db: Session = Depends(get_db)):
    rows = db.scalars(select(Draft).where(Draft.opportunity_id == opportunity_id).order_by(Draft.created_at.desc()))
    return [_out(d) for d in rows]


@router.patch("/drafts/{draft_id}", response_model=DraftOut)
def update_draft(draft_id: uuid.UUID, body: DraftUpdate, db: Session = Depends(get_db)):
    draft = db.get(Draft, draft_id)
    if draft is None:
        raise HTTPException(404, "Draft not found")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(draft, key, value)
    db.commit()
    return _out(draft)
