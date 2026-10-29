"""Find official admissions/funding pages, extract requirements, and classify funding (Planning §7.2, §8.4)."""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from urllib.parse import urlsplit

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import UnsafeURLError
from app.db.models import Department, Evidence, FundingAssessment, Professor, Program, Source, University
from app.prompts import program_extraction as prompt
from app.schemas.extraction import Claim
from app.schemas.program import ProgramExtraction
from app.services import ingestion, llm, page_finder
from app.services.extraction import _is_supported, _norm, _same_university, _ensure_aliases
from app.services.fetcher import FetchError

DEGREE_LABELS = {"phd": "PhD", "thesis_masters": "research (thesis-based) master's", "course_masters": "course-based master's"}
MAX_PAGES = 4
REVERIFY_AFTER = timedelta(days=30)

SEARCH_PROMPT = """Find the official graduate admissions and funding pages for the {degree} program at
{university} in which {professor} (department: {department}) supervises graduate students.

I need pages stating: funding guarantees or stipend amounts, tuition coverage, application
deadlines for {term}, English language test requirements (TOEFL, IELTS, PTE) and minimum GPA.
Return up to {n} URLs on the university's own website, best first, one per line, nothing else."""

# §7.2 defaults when no verified page evidence exists: (status, basis, timing, counts_for_visa_proof)
DEFAULTS = {
    ("US", "phd"): ("potential", "program_guarantee", "at_admission", None),
    ("US", "thesis_masters"): ("potential", "unknown", "after_admission", None),
    ("US", "course_masters"): ("unfunded", "unknown", "after_enrollment", False),
    ("CA", "phd"): ("potential", "supervisor", "at_admission", None),
    ("CA", "thesis_masters"): ("potential", "supervisor", "at_admission", None),
    ("CA", "course_masters"): ("unfunded", "unknown", "unknown", False),
}
SOURCE_BASIS = {"research": "research_assistantship", "teaching": "teaching_assistantship",
                "fellowship": "competitive_scholarship", "scholarship": "competitive_scholarship"}


@dataclass
class ProgramOutcome:
    program_id: uuid.UUID | None
    status: str  # verified | default_only | cached
    pages: list[dict] = field(default_factory=list)


def _registrable(host: str | None) -> str:
    return ".".join((host or "").split(".")[-2:])


def _number(value: str | None) -> float | None:
    try:
        return float(value.replace(",", "")) if value else None
    except ValueError:
        return None


def classify_funding(country: str | None, degree_type: str, verified: dict[str, str | None],
                     sources: list[str], conditions: list[str], has_unverified_claims: bool) -> dict:
    """Deterministic funding classification. LLM output only supplies quoted facts."""
    status, basis, timing, visa = DEFAULTS.get((country, degree_type), ("unknown", "unknown", "unknown", None))
    method, notes = "default", [f"No verified funding statement; default for {country or '?'} {degree_type}."]

    guaranteed = (verified.get("guaranteed_funding") or "").lower() == "yes"
    tuition = (verified.get("tuition_coverage") or "").lower() or None
    stipend = _number(verified.get("stipend_amount"))
    mentions_stipend = stipend is not None or any("stipend" in s.lower() for s in sources + conditions)

    if guaranteed and tuition == "full" and mentions_stipend:
        status, basis, timing, visa, method = "confirmed_full", "program_guarantee", "at_admission", True, "extracted"
        notes = ["Page guarantees funding with full tuition coverage and a stipend."]
        if stipend is None:
            notes.append("Stipend amount not stated.")
    elif guaranteed or tuition in ("full", "partial") or stipend is not None:
        status, method = "confirmed_partial", "extracted"
        basis = "program_guarantee" if guaranteed else next(
            (b for key, b in SOURCE_BASIS.items() for s in sources if key in s.lower()), basis)
        timing = "at_admission" if guaranteed else "unknown"
        missing = [name for name, ok in (("guarantee", guaranteed), ("full tuition", tuition == "full"),
                                         ("stipend", mentions_stipend)) if not ok]
        notes = [f"Some funding is stated; not confirmed: {', '.join(missing)}."]
    elif has_unverified_claims:
        status, method = "advertised_unverified", "extracted"
        notes = ["Funding is mentioned but the quotes could not be verified on the page."]

    international = {"yes": True, "no": False}.get((verified.get("funding_for_international_students") or "").lower())
    if international is False:
        notes.append("Page says this funding is not available to international students.")
    return {
        "funding_status": status, "basis": basis, "timing": timing, "method": method,
        "counts_for_visa_proof": visa if international is not False else False,
        "tuition_coverage": tuition or "unknown",
        "stipend_amount": stipend,
        "currency": verified.get("stipend_currency"),
        "stipend_period": verified.get("stipend_period"),
        "duration_months": int(_number(verified.get("funding_duration_years")) * 12)
        if _number(verified.get("funding_duration_years")) else None,
        "international_eligible": international,
        "explanation": " ".join(notes),
    }


def _merge(extractions: list[tuple[Source, ProgramExtraction, str]]) -> tuple[dict, dict, list, bool]:
    """Combine accepted pages: first verified value per field; collect evidence rows."""
    verified, lists, evidence, unverified_funding = {}, {"funding_sources": [], "funding_conditions": [],
                                                          "prerequisites": [], "english": []}, [], False
    for source, ex, page in extractions:
        for name in ProgramExtraction.model_fields:
            value = getattr(ex, name)
            claims = value if isinstance(value, list) else [value]
            for c in claims:
                if not isinstance(c, Claim) or c.value is None:
                    continue
                ok = _is_supported(c, page)
                evidence.append((source.id, name, c, ok))
                if not ok:
                    unverified_funding |= name in ("guaranteed_funding", "tuition_coverage", "stipend_amount")
                    continue
                if name in lists:
                    lists[name].append(c.value)
                else:
                    verified.setdefault(name, c.value)
        for t in ex.english_tests:
            if t.evidence_quote and _norm(t.evidence_quote) in page:
                lists["english"].append({"test": t.test, "minimum": t.minimum, "quote": t.evidence_quote})
    return verified, lists, evidence, unverified_funding


def _department_name(db: Session, professor: Professor) -> str | None:
    dept = db.get(Department, professor.department_id) if professor.department_id else None
    return dept.name if dept else None


def is_fresh(program: Program | None) -> bool:
    return bool(program and program.last_verified_at and datetime.now(UTC) - program.last_verified_at < REVERIFY_AFTER)


def find_cached_program(db: Session, university_id: uuid.UUID, department: str | None, degree_type: str) -> Program | None:
    if department is None:
        return None  # unknown department: can't safely reuse another professor's program
    program = db.scalars(select(Program).where(
        Program.university_id == university_id, Program.degree_type == degree_type,
        Program.department == department)).first()
    return program if is_fresh(program) else None


def verify_program(db: Session, professor_id: uuid.UUID, degree_type: str, intended_term: str | None) -> ProgramOutcome:
    professor = db.get(Professor, professor_id)
    university = db.get(University, professor.university_id)
    department = _department_name(db, professor)
    cached = find_cached_program(db, university.id, department, degree_type)
    if cached:
        return ProgramOutcome(cached.id, "cached")

    text, _ = llm.search_text(SEARCH_PROMPT.format(
        degree=DEGREE_LABELS[degree_type], university=university.name, professor=professor.name,
        department=department or "unknown", term=intended_term or "the next intake", n=MAX_PAGES,
    ), settings.extraction_model)

    trusted_domains = {_registrable(urlsplit(professor.faculty_url).hostname)} if professor.faculty_url else set()
    accepted, pages = [], []
    for url in page_finder.candidate_urls(text)[:MAX_PAGES]:
        try:
            source, _ = ingestion.ingest_url(db, url)
            page_text = (source.extracted_text or source.raw_content)[: settings.extraction_max_chars]
            result = llm.generate_structured(prompt.SYSTEM, prompt.build_user_message(source.canonical_url, page_text),
                                             ProgramExtraction, settings.extraction_model)
        except (FetchError, UnsafeURLError, llm.LLMError) as e:
            pages.append({"url": url, "result": f"failed: {e}"})
            continue
        ex, page = result.parsed, _norm(page_text)
        named = ex.university.value if _is_supported(ex.university, page) else None
        if named:
            _ensure_aliases(db, university)
        if named and not _same_university(named, university):
            pages.append({"url": url, "result": f"rejected: page is about {named!r}"})
            continue
        if not named and _registrable(source.domain) not in trusted_domains:
            pages.append({"url": url, "result": "rejected: university not stated and domain not trusted"})
            continue
        trusted_domains.add(_registrable(source.domain))
        accepted.append((source, ex, page))
        pages.append({"url": url, "result": f"accepted ({ex.page_kind})"})

    verified, lists, evidence, unverified_funding = _merge(accepted)
    name = verified.get("program_name") or f"{DEGREE_LABELS[degree_type]} ({department or 'graduate program'})"
    program = db.scalars(select(Program).where(
        Program.university_id == university.id, Program.degree_type == degree_type,
        Program.normalized_name == _norm(name))).first()
    if program is None:
        program = Program(university_id=university.id, name=name, normalized_name=_norm(name), degree_type=degree_type)
        db.add(program)
    deadline = verified.get("application_deadline")
    try:
        program.deadline = date.fromisoformat(deadline) if deadline else None
    except ValueError:
        program.deadline = None
    program.department = department
    program.deadline_raw = next((c.evidence_quote for _, n, c, ok in evidence if n == "application_deadline" and ok), None)
    program.url = accepted[0][0].canonical_url if accepted else None
    program.source_ids = [str(s.id) for s, _, _ in accepted]
    program.requirements_json = {
        "english": lists["english"], "pte_accepted": verified.get("pte_accepted"),
        "minimum_gpa": verified.get("minimum_gpa"), "requires_masters_for_phd": verified.get("requires_masters_for_phd"),
        "supervisor_required": verified.get("supervisor_required_before_admission"),
        "deadline_term": verified.get("deadline_term"), "prerequisites": lists["prerequisites"],
        "warnings": [w for _, ex, _ in accepted for w in ex.warnings], "pages": pages,
    }
    program.last_verified_at = datetime.now(UTC)
    db.flush()

    db.execute(delete(Evidence).where(Evidence.entity_type == "program", Evidence.entity_id == program.id))
    evidence_ids = []
    for source_id, field_name, claim, ok in evidence:
        row = Evidence(source_id=source_id, entity_type="program", entity_id=program.id, field_name=field_name,
                       excerpt=claim.evidence_quote or "", claim_value_json={"value": claim.value},
                       verification_status="quote_verified" if ok else "quote_not_found",
                       extractor_version=prompt.VERSION)
        db.add(row)
        db.flush()
        if ok and field_name in ("guaranteed_funding", "tuition_coverage", "stipend_amount", "funding_sources",
                                 "funding_for_international_students"):
            evidence_ids.append(str(row.id))

    funding = classify_funding(university.country, degree_type, verified, lists["funding_sources"],
                               lists["funding_conditions"], unverified_funding)
    assessment = db.scalars(select(FundingAssessment).where(FundingAssessment.program_id == program.id)).first()
    if assessment is None:
        assessment = FundingAssessment(program_id=program.id, **funding)
        db.add(assessment)
    else:
        for k, v in funding.items():
            setattr(assessment, k, v)
    assessment.conditions_json = lists["funding_conditions"]
    assessment.evidence_ids = evidence_ids
    db.commit()
    return ProgramOutcome(program.id, "verified" if accepted else "default_only", pages)
