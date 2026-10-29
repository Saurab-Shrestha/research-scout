"""MCP server exposing Research Scout tools to MCP clients (Planning §10, ADR-06).

One process, three tool groups: discovery (web), scholarly (OpenAlex), workspace (our records).
Tools call the same services as the API, so behaviour and safety checks are identical.
No generic SQL or arbitrary-write tool is exposed.

Run (stdio): uv run python -m app.mcp_server   (from backend/)
"""

import uuid
from typing import Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from app.api.v1 import professors as professors_api
from app.api.v1 import profile as profile_api
from app.api.v1 import research_jobs as jobs_api
from app.core.config import settings
from app.core.security import UnsafeURLError
from app.db.models import ResearchJob
from app.db.session import SessionLocal
from app.services import extraction, ingestion, llm, openalex, page_finder, publications
from app.services.fetcher import FetchError

server = MCPServer(
    "research-scout",
    instructions="Tools for finding funded graduate research positions. Facts from web pages are only "
                 "trustworthy when their evidence status is quote_verified; social posts are unverified leads.",
)

READ_EXTERNAL = ToolAnnotations(readOnlyHint=True, openWorldHint=True)
READ_LOCAL = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
WRITE_LOCAL = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True)


def _uuid(value: str, what: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError:
        raise ToolError(f"invalid {what}: {value!r}")


# --- Discovery ------------------------------------------------------------------------------

@server.tool(annotations=READ_EXTERNAL)
def search_web(query: str) -> dict[str, Any]:
    """Google-grounded web search via Gemini. Returns the answer text and the queries it ran.

    Treat results as leads; fetch and extract a page before relying on any fact from it.
    """
    try:
        text, queries = llm.search_text(query, settings.extraction_model)
    except llm.LLMError as e:
        raise ToolError(str(e))
    return {"answer": text, "search_queries": queries, "urls": page_finder.candidate_urls(text)}


@server.tool(annotations=WRITE_LOCAL)
def ingest_and_extract(url: str | None = None, text: str | None = None,
                       source_type: Literal["web_page", "social_post", "alert_email"] = "web_page") -> dict[str, Any]:
    """Store a public page (fetched safely, robots.txt respected) or pasted text, then extract
    academic facts with per-field evidence. Pasted text is never fetched and stays an unverified lead.
    """
    if not url and not (text and text.strip()):
        raise ToolError("provide url or text")
    with SessionLocal() as db:
        try:
            if text:
                source, _ = ingestion.ingest_text(db, text, url, "social_post" if source_type == "web_page" else source_type)
            else:
                source, _ = ingestion.ingest_url(db, url)
            outcome = extraction.extract_source(db, source.id)
        except (UnsafeURLError, FetchError, llm.LLMError) as e:
            raise ToolError(str(e))
    return {
        "source_id": str(outcome.source_id),
        "professor_id": str(outcome.professor_id) if outcome.professor_id else None,
        "page_kind": outcome.extraction.page_kind,
        "verified_fields": outcome.verified_fields,
        "unverified_fields": outcome.unverified_fields,
        "warnings": outcome.extraction.warnings,
    }


# --- Scholarly ------------------------------------------------------------------------------

@server.tool(annotations=READ_EXTERNAL)
def search_openalex_topics(query: str, limit: int = 5) -> list[dict[str, Any]]:
    """Find OpenAlex research topics (IDs like T10682) matching a phrase."""
    try:
        return openalex.search_topics(query, min(limit, 25))
    except openalex.ScholarlyError as e:
        raise ToolError(str(e))


@server.tool(annotations=READ_EXTERNAL)
def search_openalex_authors(name: str, institution_id: str | None = None, orcid: str | None = None) -> list[dict[str, Any]]:
    """Find OpenAlex author candidates. Same-name researchers are common: compare institution and works."""
    try:
        candidates = openalex.search_authors(name, institution_id, orcid)
    except openalex.ScholarlyError as e:
        raise ToolError(str(e))
    return [{"openalex_id": c.openalex_id, "name": c.name, "orcid": c.orcid, "works_count": c.works_count,
             "current_institution_ids": c.current_institution_ids} for c in candidates]


@server.tool(annotations=READ_EXTERNAL)
def get_author_works(author_id: str, from_year: int, limit: int = 20) -> list[dict[str, Any]]:
    """Recent works for an OpenAlex author ID (e.g. A5067036768), newest first."""
    try:
        works = openalex.recent_works(author_id, from_year, min(limit, 50))
    except openalex.ScholarlyError as e:
        raise ToolError(str(e))
    return [w.__dict__ for w in works]


# --- Workspace ------------------------------------------------------------------------------

@server.tool(annotations=READ_LOCAL)
def get_candidate_profile() -> dict[str, Any]:
    """The applicant's saved profile: education, skills, interests and funding requirements."""
    with SessionLocal() as db:
        current = profile_api._current(db)
        if current is None:
            raise ToolError("no candidate profile saved yet")
        return profile_api._to_out(current).model_dump()


@server.tool(annotations=READ_LOCAL)
def search_professors(query: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    """List saved professors, optionally filtered by name."""
    with SessionLocal() as db:
        return [p.model_dump(exclude={"evidence", "publications"})
                for p in professors_api.list_professors(q=query, ids=None, limit=limit, db=db)]


@server.tool(annotations=READ_LOCAL)
def get_professor(professor_id: str) -> dict[str, Any]:
    """A professor with field-level evidence and linked publications."""
    with SessionLocal() as db:
        try:
            return professors_api.get_professor(_uuid(professor_id, "professor_id"), db).model_dump()
        except professors_api.HTTPException as e:
            raise ToolError(e.detail)


@server.tool(annotations=WRITE_LOCAL)
def refresh_professor_publications(professor_id: str) -> dict[str, Any]:
    """Resolve the professor on OpenAlex (only when unambiguous) and link recent publications."""
    with SessionLocal() as db:
        try:
            o = publications.enrich_professor(db, _uuid(professor_id, "professor_id"))
        except (LookupError, openalex.ScholarlyError) as e:
            raise ToolError(str(e))
    return {"status": o.status, "reason": o.reason, "openalex_id": o.openalex_id, "confidence": o.confidence,
            "publications_linked": o.publications_linked, "candidates": o.candidates}


@server.tool(annotations=WRITE_LOCAL)
def find_faculty_page(professor_id: str) -> dict[str, Any]:
    """Search for the professor's official page; attach it only if extraction confirms the same person."""
    with SessionLocal() as db:
        try:
            o = page_finder.find_faculty_page(db, _uuid(professor_id, "professor_id"))
        except (LookupError, llm.LLMError) as e:
            raise ToolError(str(e))
    return {"status": o.status, "faculty_url": o.faculty_url, "attempts": o.attempts}


@server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True))
def start_discovery(research_areas: list[str], query: str | None = None, countries: list[Literal["US", "CA"]] = ["US", "CA"],
                    max_results: int = 30, find_pages: bool = True) -> dict[str, Any]:
    """Queue a background discovery job (a worker must be running). Poll with get_discovery_job.

    research_areas: any of machine_learning, artificial_intelligence, quantum_computing, or free text.
    """
    body = jobs_api.DiscoveryRequest(research_areas=research_areas, query=query, countries=countries,
                                     max_results=max_results, find_pages=find_pages)
    if not body.research_areas and not body.query:
        raise ToolError("provide research_areas or a query")
    with SessionLocal() as db:
        job = ResearchJob(job_type="discovery", input_json=body.model_dump())
        db.add(job)
        db.commit()
        return {"job_id": str(job.id), "status": job.status}


@server.tool(annotations=READ_LOCAL)
def get_discovery_job(job_id: str) -> dict[str, Any]:
    """Status, progress events and result summary of a discovery job."""
    with SessionLocal() as db:
        job_uuid = _uuid(job_id, "job_id")
        try:
            job = jobs_api.get_job(job_uuid, db)
        except jobs_api.HTTPException as e:
            raise ToolError(e.detail)
        events = jobs_api.job_events(job_uuid, db)
    return {"job": job.model_dump(mode="json"), "events": [e.model_dump(mode="json") for e in events]}


if __name__ == "__main__":
    server.run("stdio")
