"""Store fetched pages and pasted posts as deduplicated sources."""

import hashlib
from urllib.parse import urlsplit

import trafilatura
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.security import canonicalize_url
from app.db.models import Source
from app.services.fetcher import fetch_public_page


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _save(db: Session, **values) -> tuple[Source, bool]:
    """Insert unless (canonical_url, content_hash) exists. Returns (source, created)."""
    stmt = insert(Source).values(**values).on_conflict_do_nothing().returning(Source.id)
    new_id = db.execute(stmt).scalar()
    db.commit()
    if new_id:
        return db.get(Source, new_id), True
    existing = db.scalars(select(Source).where(
        Source.canonical_url == values["canonical_url"],
        Source.content_hash == values["content_hash"],
    )).one()
    return existing, False


def ingest_url(db: Session, url: str) -> tuple[Source, bool]:
    page = fetch_public_page(url)
    canonical = canonicalize_url(page.final_url)
    if page.content_type == "text/plain":
        extracted = page.content
    else:
        # with_metadata keeps the page <title>, which is often the only place a professor's name appears.
        extracted = trafilatura.extract(page.content, url=page.final_url, include_links=True, with_metadata=True)
    return _save(
        db,
        url=url,
        canonical_url=canonical,
        domain=urlsplit(canonical).hostname,
        source_type="web_page",
        content_hash=_sha256(page.content),
        http_status=page.status,
        content_type=page.content_type,
        raw_content=page.content,
        extracted_text=extracted,
    )


def ingest_text(db: Session, text: str, url: str | None, source_type: str) -> tuple[Source, bool]:
    """User-supplied content (e.g. a LinkedIn/Facebook post). The URL is stored, never fetched."""
    text = text.strip()
    content_hash = _sha256(text)
    canonical = canonicalize_url(url) if url else f"urn:sha256:{content_hash}"
    return _save(
        db,
        url=url,
        canonical_url=canonical,
        domain=urlsplit(canonical).hostname if url else None,
        source_type=source_type,
        content_hash=content_hash,
        content_type="text/plain",
        raw_content=text,
        extracted_text=text,
    )
