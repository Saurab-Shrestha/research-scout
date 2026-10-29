"""Postgres-backed job queue (ADR-04): claim with SKIP LOCKED, record progress events."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.models import JobEvent, ResearchJob
from app.db.session import SessionLocal

MAX_ATTEMPTS = 3
STALE_AFTER_MINUTES = 30

CLAIM_SQL = text(f"""
UPDATE research_jobs SET status = 'running', locked_at = now(), attempts = attempts + 1, updated_at = now()
WHERE id = (
    SELECT id FROM research_jobs
    WHERE status = 'queued'
       OR (status = 'running' AND locked_at < now() - interval '{STALE_AFTER_MINUTES} minutes')
    ORDER BY created_at
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
RETURNING id
""")


def claim_next(db: Session) -> uuid.UUID | None:
    job_id = db.execute(CLAIM_SQL).scalar()
    db.commit()
    return job_id


def emit(job_id: str | uuid.UUID, event_type: str, message: str, **metadata) -> None:
    with SessionLocal() as db:
        db.add(JobEvent(research_job_id=uuid.UUID(str(job_id)), event_type=event_type,
                        message=message, metadata_json=metadata))
        db.commit()


def finish(job_id: uuid.UUID, result: dict) -> None:
    with SessionLocal() as db:
        job = db.get(ResearchJob, job_id)
        job.status, job.result_json, job.error_message = "completed", result, None
        job.completed_at, job.locked_at = datetime.now(UTC), None
        db.commit()


def fail(job_id: uuid.UUID, error: str) -> str:
    """Requeue for retry (resumes from the last checkpoint) or mark failed. Returns the new status."""
    with SessionLocal() as db:
        job = db.get(ResearchJob, job_id)
        job.status = "queued" if job.attempts < MAX_ATTEMPTS else "failed"
        job.error_message, job.locked_at = error, None
        if job.status == "failed":
            job.completed_at = datetime.now(UTC)
        db.commit()
        return job.status
