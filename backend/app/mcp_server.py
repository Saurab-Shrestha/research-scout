"""MCP server exposing Research Scout tools to MCP clients (Planning §10, ADR-06).

One process, four tool groups: discovery (web), scholarly (OpenAlex), workspace (our records) and
applying (profile, tracker, drafts). Tools call the same code as the API, so behaviour and safety
checks are identical. No generic SQL, arbitrary-write or delete tool is exposed.

Run (stdio): uv run python -m app.mcp_server   (from backend/)
"""

import uuid
from datetime import UTC, date, datetime
from typing import Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from app.api.v1 import applications as applications_api
from app.api.v1 import drafts as drafts_api
from app.api.v1 import opportunities as opportunities_api
from app.api.v1 import professors as professors_api
from app.api.v1 import profile as profile_api
from app.api.v1 import research_jobs as jobs_api
from app.core.config import settings
from app.core.security import UnsafeURLError
from app.db.models import ResearchJob
from app.schemas.profile import CandidateProfileIn, Education, Experience, FundingPreferences, TestScore
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
# Changes the user's own records; destructiveHint asks MCP clients to confirm before each call.
EDIT_RECORDS = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False)


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


# --- Applying -------------------------------------------------------------------------------

@server.tool(annotations=EDIT_RECORDS)
def update_candidate_profile(name: str | None = None, career_goals: str | None = None,
                             intended_start_term: str | None = None, skills: list[str] | None = None,
                             research_interests: list[str] | None = None, test_scores: list[TestScore] | None = None,
                             education: list[Education] | None = None, experience: list[Experience] | None = None,
                             funding_preferences: FundingPreferences | None = None) -> dict[str, Any]:
    """Change fields of the applicant's profile; omitted fields are left as they are.

    A list you pass REPLACES the saved list, so call get_candidate_profile first and send the whole
    list with your change. Only record facts the user stated; never invent scores, grades or work.
    """
    changes = {k: v for k, v in locals().items() if v is not None}
    if not changes:
        raise ToolError("no fields to change")
    with SessionLocal() as db:
        current = profile_api._current(db)
        if current is None:
            raise ToolError("no candidate profile saved yet")
        before = profile_api._to_out(current).model_dump(exclude={"id"})
        merged = CandidateProfileIn.model_validate({**before, **changes})
        after = profile_api.put_profile(merged, db).model_dump(exclude={"id"})
    summary = {k: ({"before": len(before[k]), "after": len(after[k])} if isinstance(after[k], list) else "updated")
               for k in changes}
    return {"changed": summary, "profile": after}


@server.tool(annotations=READ_LOCAL)
def list_opportunities(include_excluded: bool = False, limit: int = 30) -> list[dict[str, Any]]:
    """Ranked professor × degree opportunities with funding, eligibility, deadline and score breakdown.

    The score orders a shortlist; it does not predict admission.
    """
    with SessionLocal() as db:
        rows = opportunities_api.list_opportunities(include_excluded=include_excluded, degree_type=None, country=None,
                                                    min_score=0, db=db)
    return [o.model_dump(mode="json", exclude={"explanation"}) | {"research_matches": o.explanation.get("research_matches", [])}
            for o in rows[:min(limit, 100)]]


@server.tool(annotations=READ_LOCAL)
def list_applications(include_closed: bool = True) -> list[dict[str, Any]]:
    """Tracker entries: stage, next action, deadline, contact date, notes and stage history."""
    with SessionLocal() as db:
        return [a.model_dump(mode="json") for a in applications_api.list_applications(include_closed, db)]


@server.tool(annotations=WRITE_LOCAL)
def track_opportunity(opportunity_id: str, note: str = "") -> dict[str, Any]:
    """Add an opportunity to the shortlist (the tracker's first stage). Adding it twice returns the same entry."""
    with SessionLocal() as db:
        try:
            body = applications_api.ApplicationCreate(opportunity_id=_uuid(opportunity_id, "opportunity_id"), notes=note)
            return applications_api.create_application(body, db).model_dump(mode="json")
        except applications_api.HTTPException as e:
            raise ToolError(e.detail)


@server.tool(annotations=EDIT_RECORDS)
def update_application(application_id: str, status: applications_api.Status | None = None,
                       contacted_at: date | None = None, deadline: date | None = None, next_action: str | None = None,
                       next_action_at: date | None = None, add_note: str | None = None) -> dict[str, Any]:
    """Move a tracker entry to another stage or change its dates and next action.

    Moving to "contacted" records today as the contact date unless contacted_at is given. Notes are
    only ever appended (add_note), never overwritten. Only record what the user says actually happened;
    this never sends anything.
    """
    app_id = _uuid(application_id, "application_id")
    fields = {"status": status, "contacted_at": contacted_at, "deadline": deadline, "next_action": next_action,
              "next_action_at": next_action_at}
    changes = {k: v for k, v in fields.items() if v is not None}
    with SessionLocal() as db:
        try:
            if add_note:
                current = next((a for a in applications_api.list_applications(True, db) if a.id == str(app_id)), None)
                if current is None:
                    raise ToolError("application not found")
                stamp = datetime.now(UTC).date().isoformat()
                changes["notes"] = f"{current.notes.rstrip()}\n\n{stamp}: {add_note.strip()}".strip()
            if not changes:
                raise ToolError("no changes given")
            body = applications_api.ApplicationUpdate(**changes)
            return applications_api.update_application(app_id, body, db).model_dump(mode="json")
        except applications_api.HTTPException as e:
            raise ToolError(e.detail)


@server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True))
def generate_draft(opportunity_id: str, kind: Literal["email", "follow_up", "sop_outline"] = "email") -> dict[str, Any]:
    """Write a new draft (about 10 s) from the profile, the professor's stored papers and verified program
    facts. Saved as a new version in the Writing Studio; never sent. A follow-up needs a first email.
    Show the user the warnings: they flag invented citations and placeholders to fill in.
    """
    with SessionLocal() as db:
        try:
            body = drafts_api.DraftCreate(kind=kind)
            return drafts_api.create_draft(_uuid(opportunity_id, "opportunity_id"), body, db).model_dump(mode="json")
        except drafts_api.HTTPException as e:
            raise ToolError(e.detail)


@server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True))
def evaluate_programs(degree_types: list[Literal["phd", "thesis_masters", "course_masters"]] = ["phd", "thesis_masters"],
                      professor_ids: list[str] | None = None, force: bool = False) -> dict[str, Any]:
    """Queue a background job that finds official program pages, funding, deadlines and requirements, then
    re-ranks opportunities (a worker must be running; a full run takes 15 to 20 minutes). Poll with
    get_discovery_job. force re-checks programs verified in the last 30 days.
    """
    ids = [_uuid(p, "professor_id") for p in professor_ids] if professor_ids else None
    with SessionLocal() as db:
        try:
            return opportunities_api.start_evaluation(
                opportunities_api.EvaluateRequest(professor_ids=ids, degree_types=degree_types, force=force), db)
        except opportunities_api.HTTPException as e:
            raise ToolError(e.detail)


if __name__ == "__main__":
    server.run("stdio")
