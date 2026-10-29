"""Evaluation graph: professors -> verified programs + funding -> opportunities -> scores (Milestone 3)."""

from typing import NotRequired, TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy import select

from app.db.models import CandidateProfile, Opportunity, Professor, ProfessorPublication, Program, Publication
from app.db.session import SessionLocal
from app.services import llm, matching, openalex, programs
from app.services.jobs import emit

DEGREE_TITLES = {"phd": "PhD supervision", "thesis_masters": "Thesis master's supervision",
                 "course_masters": "Course-based master's"}


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
        if db.scalars(select(CandidateProfile)).first() is None:
            raise ValueError("save a candidate profile before evaluating opportunities")
    emit(state["job_id"], "selected", f"Evaluating {len(ids)} professors × {len(state['degree_types'])} degree types")
    return {"professor_ids": ids}


def verify_programs(state: EvaluationState) -> dict:
    """One program lookup per professor and degree; reused for colleagues in the same department."""
    opportunity_ids, errors = [], []
    with SessionLocal() as db:
        profile = db.scalars(select(CandidateProfile)).first()
        for prof_id in state["professor_ids"]:
            professor = db.get(Professor, prof_id)
            for degree in state["degree_types"]:
                existing = db.scalars(select(Opportunity).join(Program).where(
                    Opportunity.professor_id == professor.id, Program.degree_type == degree)).first()
                if existing and not state.get("force") and programs.is_fresh(db.get(Program, existing.program_id)):
                    opportunity_ids.append(str(existing.id))
                    continue  # verified recently; also makes resumed runs skip finished work
                try:
                    outcome = programs.verify_program(db, professor.id, degree, profile.intended_start_term,
                                                      force=bool(state.get("force")))
                except (llm.LLMError, openalex.ScholarlyError) as e:
                    db.rollback()
                    errors.append({"professor_id": prof_id, "degree": degree, "error": str(e)})
                    continue
                opp = db.scalars(select(Opportunity).where(Opportunity.professor_id == professor.id,
                                                           Opportunity.program_id == outcome.program_id)).first()
                if opp is None:
                    opp = Opportunity(professor_id=professor.id, program_id=outcome.program_id, degree_type=degree,
                                      title=f"{DEGREE_TITLES[degree]} with {professor.name}")
                    db.add(opp)
                    db.commit()
                opportunity_ids.append(str(opp.id))
                emit(state["job_id"], "program", f"{professor.name} · {degree}: {outcome.status}", pages=outcome.pages)
    return {"opportunity_ids": opportunity_ids, "errors": errors}


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
