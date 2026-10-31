"""Discovery graph (Planning §11): topics -> active authors -> professors -> publications.

Deterministic control flow; nodes keep state small and write results to Postgres as they go.
Every write is idempotent, so a node re-run after a crash is safe.
"""

from datetime import UTC, datetime
from typing import NotRequired, TypedDict

from langgraph.graph import END, START, StateGraph

from app.core.countries import COUNTRIES
from app.db.models import Professor, ProfessorPublication
from app.db.session import SessionLocal
from app.services import discovery, llm, openalex, page_finder, publications
from app.services.jobs import emit

ALLOWED_COUNTRIES = set(COUNTRIES)
TOPIC_CANDIDATES_PER_QUERY = 5  # the planner picks from these; taking them all drifted into adjacent fields
ACTIVE_YEARS = 3


class DiscoveryState(TypedDict):
    job_id: str
    query: str | None
    countries: list[str]
    research_areas: list[str]
    max_results: int
    find_pages: NotRequired[bool]
    refresh: NotRequired[bool]  # include researchers already saved and re-link their recent papers
    topic_ids: NotRequired[list[str]]
    author_counts: NotRequired[dict[str, int]]
    professor_ids: NotRequired[list[str]]
    new_professor_ids: NotRequired[list[str]]
    skipped: NotRequired[list[dict]]
    pages: NotRequired[dict[str, str]]
    errors: NotRequired[list[dict]]
    result_summary: NotRequired[dict]


def validate_request(state: DiscoveryState) -> dict:
    bad = set(state["countries"]) - ALLOWED_COUNTRIES
    if bad or not state["countries"]:
        raise ValueError(f"countries must be a non-empty subset of {sorted(ALLOWED_COUNTRIES)}")
    if not state["research_areas"] and not state.get("query"):
        raise ValueError("provide research_areas or a query")
    if not 1 <= state["max_results"] <= 100:
        raise ValueError("max_results must be between 1 and 100")
    emit(state["job_id"], "validated", "Request validated")
    return {}


def find_topics(state: DiscoveryState) -> dict:
    candidates = {q: openalex.search_topics(q, TOPIC_CANDIDATES_PER_QUERY)
                  for q in discovery.topic_queries(state["research_areas"], state.get("query"))}
    chosen, method = discovery.choose_topics(state["research_areas"], state.get("query"), candidates)
    emit(state["job_id"], "topics", f"Selected {len(chosen)} OpenAlex topics ({method})",
         topics=[c["name"] for c in chosen], reasons=[c.get("reason") for c in chosen])
    return {"topic_ids": [c["id"] for c in chosen]}


def discover_authors(state: DiscoveryState) -> dict:
    from_year = datetime.now(UTC).year - ACTIVE_YEARS
    # Without refresh, saved researchers are skipped later, so fetch the full pool to leave room for new ones.
    limit = min(200, state["max_results"] * 5) if state.get("refresh") else 200
    authors = openalex.top_authors_for_topics(state["topic_ids"], state["countries"], from_year, limit=limit)
    emit(state["job_id"], "authors", f"Found {len(authors)} active authors since {from_year}")
    return {"author_counts": {a["id"]: a["topic_works"] for a in authors}}


def persist_candidates(state: DiscoveryState) -> dict:
    counts = state["author_counts"]
    authors = openalex.get_authors(list(counts))
    ids, new_ids = [], []
    with SessionLocal() as db:
        known = set() if state.get("refresh") else discovery.known_keys(db)
        kept, skipped = discovery.select_candidates(
            authors, counts, state["countries"], datetime.now(UTC).year, state["max_results"], known,
        )
        for c in kept:
            prof_id, created = discovery.upsert_candidate(db, c)
            ids.append(str(prof_id))
            if created:
                new_ids.append(str(prof_id))
    already = sum(s["reason"].startswith("already") for s in skipped)
    emit(state["job_id"], "professors",
         f"Kept {len(kept)} professors ({len(new_ids)} new), skipped {len(skipped)} ({already} already in your list)")
    return {"professor_ids": ids, "new_professor_ids": new_ids, "skipped": skipped}


def enrich_publications(state: DiscoveryState) -> dict:
    errors = []
    with SessionLocal() as db:
        for prof_id in state["professor_ids"]:
            has_pubs = db.query(ProfessorPublication).filter_by(professor_id=prof_id).first()
            if has_pubs and not state.get("refresh"):
                continue  # already enriched by an earlier job or an interrupted run of this node
            professor = db.get(Professor, prof_id)
            try:
                publications.link_recent_works(db, professor.id, professor.openalex_id, confidence=0.7, limit=10)
                db.commit()
            except openalex.ScholarlyError as e:
                db.rollback()
                errors.append({"professor_id": prof_id, "error": str(e)})
    emit(state["job_id"], "publications", f"Linked publications ({len(errors)} errors)")
    return {"errors": errors}


def find_faculty_pages(state: DiscoveryState) -> dict:
    """Attach verified faculty pages to professors that have none. Re-runs skip ones already found."""
    pages, errors = {}, list(state.get("errors", []))
    with SessionLocal() as db:
        for prof_id in state["professor_ids"]:
            professor = db.get(Professor, prof_id)
            if professor.faculty_url:
                pages[prof_id] = "existing"
                continue
            try:
                outcome = page_finder.find_faculty_page(db, professor.id)
            except llm.LLMError as e:
                errors.append({"professor_id": prof_id, "error": str(e)})
                continue
            pages[prof_id] = outcome.status
            emit(state["job_id"], "page", f"{professor.name}: {outcome.status}",
                 url=outcome.faculty_url, attempts=outcome.attempts)
    found = sum(v != "not_found" for v in pages.values())
    emit(state["job_id"], "pages", f"Faculty pages verified for {found}/{len(pages)} professors")
    return {"pages": pages, "errors": errors}


def finalize(state: DiscoveryState) -> dict:
    summary = {
        "topics": len(state.get("topic_ids", [])),
        "professors": len(state.get("professor_ids", [])),
        "new_professors": len(state.get("new_professor_ids", [])),
        "skipped": len(state.get("skipped", [])),
        "faculty_pages": sum(v != "not_found" for v in state.get("pages", {}).values()),
        "errors": state.get("errors", []),
        "professor_ids": state.get("professor_ids", []),
    }
    emit(state["job_id"], "completed", f"Discovery finished: {summary['professors']} professors")
    return {"result_summary": summary}


def build_graph(checkpointer):
    g = StateGraph(DiscoveryState)
    for node in (validate_request, find_topics, discover_authors, persist_candidates, enrich_publications,
                 find_faculty_pages, finalize):
        g.add_node(node.__name__, node)
    g.add_edge(START, "validate_request")
    g.add_edge("validate_request", "find_topics")
    g.add_conditional_edges("find_topics", lambda s: "discover_authors" if s["topic_ids"] else "finalize")
    g.add_edge("discover_authors", "persist_candidates")
    g.add_edge("persist_candidates", "enrich_publications")
    g.add_conditional_edges("enrich_publications",
                            lambda s: "find_faculty_pages" if s.get("find_pages", True) else "finalize")
    g.add_edge("find_faculty_pages", "finalize")
    g.add_edge("finalize", END)
    return g.compile(checkpointer=checkpointer)
