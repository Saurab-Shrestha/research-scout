"""Find and verify a discovered professor's official faculty or lab page."""

import re
import uuid
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import UnsafeURLError, canonicalize_url
from app.db.models import Professor, University
from app.services import extraction, ingestion, llm
from app.services.publications import _name_key
from app.services.fetcher import FetchError

MAX_CANDIDATES = 3
URL_RE = re.compile(r"(?:https?://|www\.)[^\s<>\"')\]]+")
# Profiles here are not primary sources, or cannot be fetched under their terms (§7.3).
BLOCKED_DOMAINS = (
    "linkedin.com", "facebook.com", "x.com", "twitter.com", "researchgate.net", "scholar.google.com",
    "wikipedia.org", "ratemyprofessors.com", "orcid.org", "openalex.org", "semanticscholar.org",
    "dblp.org", "academia.edu", "vertexaisearch.cloud.google.com", "youtube.com",
)

PROMPT = """Find the official faculty profile page or personal academic/lab homepage for
{name}, a researcher at {university}.

Prefer pages hosted on the university's own domains. Do not return social media, Google Scholar,
ResearchGate, Wikipedia or publication-index pages.
Reply with up to {n} URLs, best first, one per line, and nothing else. Reply NONE if not found."""


@dataclass
class PageSearchOutcome:
    status: str  # found | not_found
    faculty_url: str | None = None
    attempts: list[dict] = field(default_factory=list)
    search_queries: list[str] = field(default_factory=list)
    answer: str = ""  # Gemini's raw reply, kept for debugging misses


def _blocked(url: str) -> bool:
    host = urlsplit(url).hostname or ""
    return any(host == d or host.endswith("." + d) for d in BLOCKED_DOMAINS)


def candidate_urls(text: str) -> list[str]:
    urls = []
    for raw in URL_RE.findall(text):
        raw = raw.rstrip(".,;")
        url = canonicalize_url(raw if raw.startswith("http") else f"https://{raw}")
        if not _blocked(url) and url not in urls:
            urls.append(url)
    return urls[:MAX_CANDIDATES]


def find_faculty_page(db: Session, professor_id: uuid.UUID) -> PageSearchOutcome:
    professor = db.get(Professor, professor_id)
    if professor is None:
        raise LookupError(f"professor {professor_id} not found")
    university = db.get(University, professor.university_id) if professor.university_id else None

    prompt = PROMPT.format(
        # First + last name only: full patronymics/middle names make searches miss.
        name=" ".join(_name_key(professor.name)).title(),
        university=university.name if university else "an unknown university",
        n=MAX_CANDIDATES,
    )
    text, queries = llm.search_text(prompt, settings.extraction_model)
    if not candidate_urls(text):  # grounded replies are occasionally empty; one retry is cheap
        text, queries = llm.search_text(prompt, settings.extraction_model)
    outcome = PageSearchOutcome("not_found", search_queries=queries, answer=text[:500])
    for url in candidate_urls(text):
        try:
            source, _ = ingestion.ingest_url(db, url)
            result = extraction.extract_source(db, source.id, expected_professor_id=professor.id)
        except (FetchError, UnsafeURLError, llm.LLMError) as e:
            outcome.attempts.append({"url": url, "result": f"failed: {e}"})
            continue
        if result.professor_id:
            db.refresh(professor)
            outcome.status, outcome.faculty_url = "found", professor.faculty_url or url
            outcome.attempts.append({"url": url, "result": "verified"})
            break
        outcome.attempts.append({"url": url, "result": result.rejection or f"not a profile page ({result.extraction.page_kind})"})
    return outcome
