import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.countries import CountryCode
from app.db.models import JobEvent, ResearchJob
from app.db.session import get_db

router = APIRouter(prefix="/research-jobs", tags=["research-jobs"])


class DiscoveryRequest(BaseModel):
    job_type: Literal["discovery"] = "discovery"
    query: str | None = None
    countries: list[CountryCode] = Field(["US", "CA"], min_length=1)
    degree_types: list[Literal["phd", "thesis_masters", "course_masters"]] = ["phd", "thesis_masters"]
    research_areas: list[str] = []
    funding_priority: Literal["full_funding", "any"] = "full_funding"
    seed_urls: list[str] = []
    max_results: int = Field(30, ge=1, le=100)
    find_pages: bool = True  # search for and verify faculty pages (Gemini + Google Search)
    refresh: bool = False  # also return researchers already saved and refresh their papers; default skips them


class JobOut(BaseModel):
    id: str
    job_type: str
    status: str
    input: dict
    result: dict | None
    error_message: str | None
    attempts: int
    tokens_used: int
    cost_usd: float
    created_at: datetime
    completed_at: datetime | None


class EventOut(BaseModel):
    id: str
    event_type: str
    message: str
    metadata: dict
    created_at: datetime


def _job_out(j: ResearchJob) -> JobOut:
    return JobOut(id=str(j.id), job_type=j.job_type, status=j.status, input=j.input_json, result=j.result_json,
                  error_message=j.error_message, attempts=j.attempts, tokens_used=j.tokens_used, cost_usd=j.cost_usd, created_at=j.created_at,
                  completed_at=j.completed_at)


@router.post("", response_model=JobOut, status_code=202)
def create_job(body: DiscoveryRequest, response: Response, db: Session = Depends(get_db),
               idempotency_key: str | None = Header(None)):
    if not body.research_areas and not (body.query and body.query.strip()):
        raise HTTPException(422, "Provide research_areas or a query")
    if idempotency_key:
        existing = db.scalars(select(ResearchJob).where(ResearchJob.idempotency_key == idempotency_key)).first()
        if existing:
            response.status_code = 200
            return _job_out(existing)
    job = ResearchJob(job_type=body.job_type, input_json=body.model_dump(), idempotency_key=idempotency_key)
    db.add(job)
    db.commit()
    db.refresh(job)
    return _job_out(job)


@router.get("", response_model=list[JobOut])
def list_jobs(limit: int = 20, db: Session = Depends(get_db)):
    return [_job_out(j) for j in db.scalars(
        select(ResearchJob).order_by(ResearchJob.created_at.desc()).limit(min(limit, 100)))]


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: uuid.UUID, db: Session = Depends(get_db)):
    job = db.get(ResearchJob, job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    return _job_out(job)


@router.get("/{job_id}/events", response_model=list[EventOut])
def job_events(job_id: uuid.UUID, db: Session = Depends(get_db)):
    events = db.scalars(select(JobEvent).where(JobEvent.research_job_id == job_id)
                        .order_by(JobEvent.created_at, JobEvent.id))
    return [EventOut(id=str(e.id), event_type=e.event_type, message=e.message,
                     metadata=e.metadata_json, created_at=e.created_at) for e in events]
