"""Structured extraction from a stored source, with field-level evidence (Planning §13.2)."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlsplit

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Department, Evidence, Professor, Source, University
from app.prompts import extraction as prompt
from app.schemas.extraction import Claim, PageExtraction
from app.services import llm

PROFILE_PAGE_KINDS = {"faculty_profile", "lab_page"}


@dataclass
class ExtractionOutcome:
    source_id: uuid.UUID
    extraction: PageExtraction
    professor_id: uuid.UUID | None
    verified_fields: int
    unverified_fields: int
    input_tokens: int
    output_tokens: int
    rejection: str | None = None  # why the page was not attached to the expected professor


def _norm(text: str) -> str:
    return " ".join(text.split()).casefold()


def _is_supported(claim: Claim, page: str) -> bool:
    # ponytail: exact match after whitespace/case folding; add fuzzy matching if evals show
    # the model normalising punctuation in quotes.
    return bool(claim.value and claim.evidence_quote and _norm(claim.evidence_quote) in page)


def _claims(ex: PageExtraction):
    for field in PageExtraction.model_fields:
        value = getattr(ex, field)
        if isinstance(value, Claim):
            yield field, value
        elif isinstance(value, list):
            yield from ((field, c) for c in value if isinstance(c, Claim))


def _get_or_create(db: Session, model, lookup: dict, **defaults):
    row = db.scalars(select(model).filter_by(**lookup)).first()
    if row is None:
        row = model(**lookup, **defaults)
        db.add(row)
        db.flush()
    return row


def _same_university(page_name: str, university: University) -> bool:
    page = _norm(page_name).removeprefix("the ")
    for known in [university.name, *(university.aliases or [])]:
        known = _norm(known).removeprefix("the ")
        if known in page or page in known:
            return True
    return False


def _ensure_aliases(db: Session, university: University) -> None:
    if university.aliases is None and university.openalex_id:
        from app.services import openalex  # local import keeps extraction usable without network in tests
        try:
            university.aliases = openalex.institution_aliases(university.openalex_id)
        except openalex.ScholarlyError:
            return  # retry next time; comparison falls back to the display name
        db.flush()


def check_expected_professor(db: Session, professor: Professor, ex: PageExtraction, ok) -> str | None:
    """Return a rejection reason if the page describes someone other than `professor`."""
    from app.services.publications import _name_key  # local import: publications imports ingestion

    if not ok(ex.professor_name):
        return "page does not name a single professor"
    if _name_key(ex.professor_name.value) != _name_key(professor.name):
        return f"page is about {ex.professor_name.value!r}, not {professor.name!r}"
    university = db.get(University, professor.university_id) if professor.university_id else None
    if university and ok(ex.university):
        _ensure_aliases(db, university)
    if university and ok(ex.university) and not _same_university(ex.university.value, university):
        return f"page says {ex.university.value!r}, OpenAlex says {university.name!r}"
    return None


def _upsert_professor(db: Session, source: Source, ex: PageExtraction, ok,
                      existing: Professor | None = None) -> Professor:
    if existing is not None:
        return _update_from_page(db, existing, source, ex, ok)

    university = department = None
    if ok(ex.university):
        name = ex.university.value.strip()
        university = _get_or_create(
            db, University, {"normalized_name": name.casefold().removeprefix("the ")},
            name=name,  # country comes from OpenAlex; domains are unreliable (cs.toronto.edu)
        )
        if ok(ex.department):
            department = _get_or_create(
                db, Department, {"university_id": university.id, "name": ex.department.value.strip()},
            )

    professor = _get_or_create(db, Professor, {"faculty_url": source.canonical_url}, name=ex.professor_name.value.strip())
    professor.name = ex.professor_name.value.strip()
    professor.university_id = university.id if university else professor.university_id
    professor.department_id = department.id if department else professor.department_id
    return _apply_page_fields(professor, ex, ok)


def _update_from_page(db: Session, professor: Professor, source: Source, ex: PageExtraction, ok) -> Professor:
    """Attach a verified faculty page to a professor found through OpenAlex.

    Keeps the OpenAlex university (avoids near-duplicate university rows from page wording).
    """
    url_owner = db.scalars(select(Professor).where(Professor.faculty_url == source.canonical_url)).first()
    if professor.faculty_url is None and url_owner is None:
        professor.faculty_url = source.canonical_url
    if professor.university_id and ok(ex.department):
        professor.department_id = _get_or_create(
            db, Department, {"university_id": professor.university_id, "name": ex.department.value.strip()},
        ).id
    return _apply_page_fields(professor, ex, ok)


def _apply_page_fields(professor: Professor, ex: PageExtraction, ok) -> Professor:
    if ok(ex.professor_title):
        professor.title = ex.professor_title.value
    if ok(ex.institutional_email):
        professor.email = ex.institutional_email.value
    if ok(ex.accepting_students):
        professor.accepting_students = {"yes": True, "no": False}.get(ex.accepting_students.value.lower())
    topics = [c.value for c in ex.research_topics if ok(c)]
    if topics:
        professor.research_summary = "; ".join(topics)
    professor.last_verified_at = datetime.now(UTC)
    return professor


def extract_source(db: Session, source_id: uuid.UUID, expected_professor_id: uuid.UUID | None = None) -> ExtractionOutcome:
    source = db.get(Source, source_id)
    if source is None:
        raise LookupError(f"source {source_id} not found")

    text = (source.extracted_text or source.raw_content)[: settings.extraction_max_chars]
    result = llm.generate_structured(
        prompt.SYSTEM,
        prompt.build_user_message(source.url or source.canonical_url, text),
        PageExtraction,
        settings.extraction_model,
    )
    ex = result.parsed
    page = _norm(text)

    def ok(claim: Claim) -> bool:
        return _is_supported(claim, page)

    # Social posts and alert emails are leads (§7.3): never create entities from them directly.
    professor = rejection = None
    expected = db.get(Professor, expected_professor_id) if expected_professor_id else None
    if expected is not None:
        rejection = check_expected_professor(db, expected, ex, ok)
    if source.source_type == "web_page" and ex.page_kind in PROFILE_PAGE_KINDS and ok(ex.professor_name) and not rejection:
        professor = _upsert_professor(db, source, ex, ok, existing=expected)

    # Re-running extraction replaces this extractor version's evidence for the source.
    db.execute(delete(Evidence).where(
        Evidence.source_id == source.id, Evidence.extractor_version == prompt.VERSION,
    ))
    entity_type, entity_id = ("professor", professor.id) if professor else ("source", source.id)
    verified = unverified = 0
    for field, claim in _claims(ex):
        if claim.value is None:
            continue
        supported = ok(claim)
        verified += supported
        unverified += not supported
        if source.source_type != "web_page":
            status = "lead_unverified"
        else:
            status = "quote_verified" if supported else "quote_not_found"
        db.add(Evidence(
            source_id=source.id,
            entity_type=entity_type,
            entity_id=entity_id,
            field_name=field,
            excerpt=claim.evidence_quote or "",
            claim_value_json={"value": claim.value},
            verification_status=status,
            extractor_version=prompt.VERSION,
        ))
    db.commit()

    return ExtractionOutcome(
        source_id=source.id,
        extraction=ex,
        professor_id=professor.id if professor else None,
        verified_fields=verified,
        unverified_fields=unverified,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        rejection=rejection,
    )
