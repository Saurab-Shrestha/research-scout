"""Discovery graph (Planning §11): topics -> active authors -> professors -> publications.

Deterministic control flow; nodes keep state small and write results to Postgres as they go.
Every write is idempotent, so a node re-run after a crash is safe.
"""

from datetime import UTC, datetime
from typing import NotRequired, TypedDict

from langgraph.graph import END, START, StateGraph

from app.db.models import Professor, ProfessorPublication
from app.db.session import SessionLocal
from app.services import discovery, openalex, publications
from app.services.jobs import emit

ALLOWED_COUNTRIES = {"US", "CA"}
TOPICS_PER_QUERY = 1  # more topics per query drifted into adjacent fields (e.g. condensed matter)
ACTIVE_YEARS = 3


class DiscoveryState(TypedDict):
    job_id: str
    query: str | None
    countries: list[str]
    research_areas: list[str]
    max_results: int
    topic_ids: NotRequired[list[str]]
    author_counts: NotRequired[dict[str, int]]
    professor_ids: NotRequired[list[str]]
    new_professor_ids: NotRequired[list[str]]
    skipped: NotRequired[list[dict]]
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
    # ponytail: deterministic topic search; add the LLM search planner (§13.1) if topic recall is poor.
    topics = {}
    for q in discovery.topic_queries(state["research_areas"], state.get("query")):
        for t in openalex.search_topics(q, TOPICS_PER_QUERY):
            topics[t["id"]] = t["name"]
    emit(state["job_id"], "topics", f"Matched {len(topics)} OpenAlex topics", topics=list(topics.values()))
    return {"topic_ids": list(topics)}


def discover_authors(state: DiscoveryState) -> dict:
    from_year = datetime.now(UTC).year - ACTIVE_YEARS
    authors = openalex.top_authors_for_topics(
        state["topic_ids"], state["countries"], from_year, limit=min(200, state["max_results"] * 5),
    )
    emit(state["job_id"], "authors", f"Found {len(authors)} active authors since {from_year}")
    return {"author_counts": {a["id"]: a["topic_works"] for a in authors}}


def persist_candidates(state: DiscoveryState) -> dict:
    counts = state["author_counts"]
    authors = openalex.get_authors(list(counts))
    kept, skipped = discovery.select_candidates(
        authors, counts, state["countries"], datetime.now(UTC).year, state["max_results"],
    )
    ids, new_ids = [], []
    with SessionLocal() as db:
        for c in kept:
            prof_id, created = discovery.upsert_candidate(db, c)
            ids.append(str(prof_id))
            if created:
                new_ids.append(str(prof_id))
    emit(state["job_id"], "professors",
         f"Kept {len(kept)} professors ({len(new_ids)} new), skipped {len(skipped)}")
    return {"professor_ids": ids, "new_professor_ids": new_ids, "skipped": skipped}


def enrich_publications(state: DiscoveryState) -> dict:
    errors = []
    with SessionLocal() as db:
        for prof_id in state["professor_ids"]:
            has_pubs = db.query(ProfessorPublication).filter_by(professor_id=prof_id).first()
            if has_pubs:
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


def finalize(state: DiscoveryState) -> dict:
    summary = {
        "topics": len(state.get("topic_ids", [])),
        "professors": len(state.get("professor_ids", [])),
        "new_professors": len(state.get("new_professor_ids", [])),
        "skipped": len(state.get("skipped", [])),
        "errors": state.get("errors", []),
        "professor_ids": state.get("professor_ids", []),
    }
    emit(state["job_id"], "completed", f"Discovery finished: {summary['professors']} professors")
    return {"result_summary": summary}


def build_graph(checkpointer):
    g = StateGraph(DiscoveryState)
    for node in (validate_request, find_topics, discover_authors, persist_candidates, enrich_publications, finalize):
        g.add_node(node.__name__, node)
    g.add_edge(START, "validate_request")
    g.add_edge("validate_request", "find_topics")
    g.add_conditional_edges("find_topics", lambda s: "discover_authors" if s["topic_ids"] else "finalize")
    g.add_edge("discover_authors", "persist_candidates")
    g.add_edge("persist_candidates", "enrich_publications")
    g.add_edge("enrich_publications", "finalize")
    g.add_edge("finalize", END)
    return g.compile(checkpointer=checkpointer)
