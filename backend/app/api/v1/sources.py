import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.security import UnsafeURLError
from app.db.session import get_db
from app.schemas.source import ExtractResponse, IngestRequest, IngestResponse
from app.services import extraction, ingestion
from app.services.fetcher import FetchError
from app.services.llm import LLMError

router = APIRouter(prefix="/sources", tags=["sources"])


@router.post("/ingest", response_model=IngestResponse)
def ingest(body: IngestRequest, db: Session = Depends(get_db)):
    try:
        if body.text:
            source, created = ingestion.ingest_text(db, body.text, body.url, body.source_type)
        else:
            source, created = ingestion.ingest_url(db, body.url)
    except UnsafeURLError as e:
        raise HTTPException(400, f"URL rejected: {e}")
    except FetchError as e:
        raise HTTPException(422, f"Fetch failed: {e}")
    return IngestResponse(
        source_id=str(source.id),
        canonical_url=source.canonical_url,
        content_hash=source.content_hash,
        created=created,
    )


@router.post("/{source_id}/extract", response_model=ExtractResponse)
def extract(source_id: uuid.UUID, db: Session = Depends(get_db)):
    """Run (or re-run) structured extraction on a stored source. Uses cached content, no refetch."""
    try:
        outcome = extraction.extract_source(db, source_id)
    except LookupError:
        raise HTTPException(404, "Source not found")
    except LLMError as e:
        raise HTTPException(502, f"Extraction failed: {e}")
    return ExtractResponse(
        source_id=str(outcome.source_id),
        professor_id=str(outcome.professor_id) if outcome.professor_id else None,
        page_kind=outcome.extraction.page_kind,
        verified_fields=outcome.verified_fields,
        unverified_fields=outcome.unverified_fields,
        warnings=outcome.extraction.warnings,
        input_tokens=outcome.input_tokens,
        output_tokens=outcome.output_tokens,
    )
