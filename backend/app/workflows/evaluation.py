"""Evaluation graph: professors -> verified programs + funding -> opportunities -> scores (Milestone 3)."""

import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import NotRequired, TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy import select

from app.db.models import CandidateProfile, Opportunity, Professor, ProfessorPublication, Program, Publication
from app.db.session import SessionLocal
from app.services import llm, matching, openalex, programs
from app.services.jobs import emit

DEGREE_TITLES = {"phd": "PhD supervision", "thesis_masters": "Thesis master's supervision",
                 "course_masters": "Course-based master's", "bachelors": "Undergraduate study"}


class EvaluationState(TypedDict):
    job_id: str
    professor_ids: list[str]
    degree_types: list[str]
    force: NotRequired[bool]
    opportunity_ids: NotRequired[list[str]]
    errors: NotRequired[list[dict]]
    result_summary: NotRequired[dict]


def select_professors(state: EvaluationState) -> dict:
    with SessionLocal() as db:
        if state["professor_ids"]:
            ids = state["professor_ids"]
        else:
            ids = [str(i) for i in db.scalars(select(Professor.id).where(Professor.university_id.is_not(None)))]
        profile = db.scalars(select(CandidateProfile)).first()
        if profile is None:
            raise ValueError("save a candidate profile before evaluating opportunities")
        degrees = state["degree_types"] or profile.target_degrees
    emit(state["job_id"], "selected", f"Evaluating {len(ids)} professors × {len(degrees)} degree types")
    return {"professor_ids": ids, "degree_types": degrees}


PARALLEL_LOOKUPS = 5  # ponytail: fixed pool; lower it if Vertex starts returning 429s


def _verify_pair(job_id: str, prof_id: str, degree: str, force: bool) -> tuple[str | None, dict | None]:
    """Verify one professor × degree in its own session. Returns (opportunity_id, error)."""
    with SessionLocal() as db:
        profile = db.scalars(select(CandidateProfile)).first()
        professor = db.get(Professor, prof_id)
        existing = db.scalars(select(Opportunity).where(
            Opportunity.professor_id == professor.id, Opportunity.degree_type == degree)).first()
        if existing and not force and programs.is_fresh(db.get(Program, existing.program_id)):
            return str(existing.id), None  # verified recently; also makes resumed runs skip finished work
        try:
            outcome = programs.verify_program(db, professor.id, degree, profile.intended_start_term, force=force)
        except (llm.LLMError, openalex.ScholarlyError) as e:
            db.rollback()
            return None, {"professor_id": prof_id, "degree": degree, "error": str(e)}
        opp = db.scalars(select(Opportunity).where(Opportunity.professor_id == professor.id,
                                                   Opportunity.degree_type == degree)).first()
        if opp is None:
            opp = Opportunity(professor_id=professor.id, program_id=outcome.program_id, degree_type=degree,
                              title=f"{DEGREE_TITLES[degree]} with {professor.name}")
            db.add(opp)
        opp.program_id = outcome.program_id
        db.commit()
        emit(job_id, "program", f"{professor.name} · {degree}: {outcome.status}", pages=outcome.pages)
        return str(opp.id), None


def verify_programs(state: EvaluationState) -> dict:
    """Pairs at the same university and degree run in order, so colleagues reuse the first lookup and never
    race to create the same program; different universities run in parallel."""
    force = bool(state.get("force"))
    with SessionLocal() as db:
        universities = dict(db.execute(select(Professor.id, Professor.university_id)
                                       .where(Professor.id.in_(state["professor_ids"]))).all())
    groups: dict[tuple, list[tuple[str, str]]] = {}
    for prof_id in state["professor_ids"]:
        for degree in state["degree_types"]:
            groups.setdefault((universities.get(uuid.UUID(prof_id)), degree), []).append((prof_id, degree))

    def run_group(pairs):
        return [_verify_pair(state["job_id"], prof_id, degree, force) for prof_id, degree in pairs]

    with ThreadPoolExecutor(PARALLEL_LOOKUPS) as pool:
        results = [r for group in pool.map(run_group, groups.values()) for r in group]
    return {"opportunity_ids": [o for o, _ in results if o], "errors": [e for _, e in results if e]}


def embed_research(state: EvaluationState) -> dict:
    with SessionLocal() as db:
        profile = db.scalars(select(CandidateProfile)).first()
        pubs = db.scalars(select(Publication).join(ProfessorPublication)
                          .where(ProfessorPublication.professor_id.in_(state["professor_ids"]))).all()
        matching.ensure_embeddings(db, profile, list(pubs))
    emit(state["job_id"], "embeddings", f"Embedded research for {len(pubs)} publications")
    return {}


def score(state: EvaluationState) -> dict:
    with SessionLocal() as db:
        profile = db.scalars(select(CandidateProfile)).first()
        for opp_id in state["opportunity_ids"]:
            matching.score_opportunity(db, profile, db.get(Opportunity, opp_id))
    emit(state["job_id"], "scored", f"Scored {len(state['opportunity_ids'])} opportunities")
    return {}


def finalize(state: EvaluationState) -> dict:
    summary = {"opportunities": len(state.get("opportunity_ids", [])), "errors": state.get("errors", [])}
    emit(state["job_id"], "completed", f"Evaluation finished: {summary['opportunities']} opportunities")
    return {"result_summary": summary}


def build_graph(checkpointer):
    g = StateGraph(EvaluationState)
    nodes = (select_professors, verify_programs, embed_research, score, finalize)
    for node in nodes:
        g.add_node(node.__name__, node)
    g.add_edge(START, nodes[0].__name__)
    for a, b in zip(nodes, nodes[1:]):
        g.add_edge(a.__name__, b.__name__)
    g.add_edge(nodes[-1].__name__, END)
    return g.compile(checkpointer=checkpointer)
