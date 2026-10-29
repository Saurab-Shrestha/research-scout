"""Job worker: claims queued research jobs and runs them through LangGraph with Postgres checkpoints.

Run: uv run python -m app.worker   (from backend/, or with PYTHONPATH=backend)
"""

import logging
import time
import uuid

from langgraph.checkpoint.postgres import PostgresSaver

from app.core.config import settings
from app.db.models import ResearchJob
from app.db.session import SessionLocal
from app.services import jobs
from app.workflows import discovery

log = logging.getLogger("worker")
POLL_SECONDS = 2


def initial_state(job: ResearchJob) -> dict:
    data = job.input_json
    return {
        "job_id": str(job.id),
        "query": data.get("query"),
        "countries": data.get("countries", []),
        "research_areas": data.get("research_areas", []),
        "max_results": data.get("max_results", 30),
    }


def run_job(graph, job_id: uuid.UUID) -> str:
    """Run or resume one job. Returns its final status."""
    config = {"configurable": {"thread_id": str(job_id)}}
    with SessionLocal() as db:
        job = db.get(ResearchJob, job_id)
        state = initial_state(job)
    try:
        if graph.get_state(config).next:
            jobs.emit(job_id, "resumed", "Resuming from last checkpoint")
            result = graph.invoke(None, config)
        else:
            jobs.emit(job_id, "started", "Discovery started")
            result = graph.invoke(state, config)
    except Exception as e:  # noqa: BLE001 - any node failure is recorded and retried
        log.exception("job %s failed", job_id)
        status = jobs.fail(job_id, f"{type(e).__name__}: {e}")
        jobs.emit(job_id, "error", f"{type(e).__name__}: {e}", will_retry=status == "queued")
        return status
    jobs.finish(job_id, result.get("result_summary", {}))
    return "completed"


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    conn = settings.database_url.replace("postgresql+psycopg://", "postgresql://")
    with PostgresSaver.from_conn_string(conn) as checkpointer:
        checkpointer.setup()
        graph = discovery.build_graph(checkpointer)
        log.info("worker started")
        # ponytail: one job at a time; run more worker processes if throughput matters.
        while True:
            with SessionLocal() as db:
                job_id = jobs.claim_next(db)
            if job_id is None:
                time.sleep(POLL_SECONDS)
                continue
            log.info("job %s -> %s", job_id, run_job(graph, job_id))


if __name__ == "__main__":
    main()
