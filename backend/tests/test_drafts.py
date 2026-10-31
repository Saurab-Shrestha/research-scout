from langgraph.checkpoint.memory import InMemorySaver

from app.db.models import ResearchJob
from app.db.session import SessionLocal
from app.schemas.drafts import EmailDraft, SopOutline, SopSection
from app.services import ingestion, llm
from app.services.fetcher import FetchResult
from app.worker import run_job
from app.workflows import evaluation
from tests.test_milestone3 import ADMISSIONS, program_extraction, seed


def scored_opportunity(client, monkeypatch) -> str:
    prof_id = seed()
    monkeypatch.setattr(llm, "search_text", lambda prompt, model=None: ("https://grad.example.edu/phd", []))
    monkeypatch.setattr(ingestion, "fetch_public_page", lambda url: FetchResult(url, 200, "text/plain", ADMISSIONS))
    monkeypatch.setattr(llm, "generate_structured", lambda *a: llm.LLMResult(program_extraction(), "m", 1, 1))
    monkeypatch.setattr(llm, "embed", lambda texts: [[1.0, 0.0] for _ in texts])
    with SessionLocal() as db:
        job = ResearchJob(job_type="evaluation", status="running", attempts=1,
                          input_json={"professor_ids": [str(prof_id)], "degree_types": ["phd"]})
        db.add(job)
        db.commit()
    run_job({"evaluation": evaluation.build_graph(InMemorySaver())}, job.id)
    return client.get("/api/v1/opportunities").json()[0]["id"]


def test_email_draft_flags_invented_citations_and_saves_edits(client, monkeypatch):
    opp_id = scored_opportunity(client, monkeypatch)
    seen = {}

    def fake(system, user, schema, model=None):
        seen["user"] = user
        return llm.LLMResult(EmailDraft(subject="PhD Fall 2027 inquiry", body="Dear Prof. Lovelace, [lab name] ...",
                                        cited_papers=["Quantum machine learning", "A Paper That Does Not Exist"]),
                             "m", 1, 1)
    monkeypatch.setattr(llm, "generate_structured", fake)

    r = client.post(f"/api/v1/opportunities/{opp_id}/drafts", json={"kind": "email"})
    assert r.status_code == 201
    draft = r.json()
    assert "Quantum machine learning" in seen["user"] and "Fall 2027" in seen["user"]
    assert len(draft["cited_publication_ids"]) == 1
    assert any("A Paper That Does Not Exist" in w for w in draft["warnings"])
    assert any("placeholders" in w for w in draft["warnings"])
    sources = draft["sources"]  # traceable to the profile, papers and program pages it was built from
    assert sources["profile_id"] and sources["program_id"] and len(sources["publication_ids"]) == 1
    assert sources["program_source_ids"] and "context" not in sources

    edited = client.patch(f"/api/v1/drafts/{draft['id']}", json={"body": "Dear Professor Lovelace, ..."}).json()
    assert edited["body"].startswith("Dear Professor") and edited["subject"] == "PhD Fall 2027 inquiry"
    assert len(client.get(f"/api/v1/opportunities/{opp_id}/drafts").json()) == 1


def test_sop_outline_is_rendered_as_markdown(client, monkeypatch):
    opp_id = scored_opportunity(client, monkeypatch)
    outline = SopOutline(sections=[SopSection(heading="Motivation", points=["OCR work", "RAG systems"])],
                         cited_papers=[])
    monkeypatch.setattr(llm, "generate_structured", lambda *a: llm.LLMResult(outline, "m", 1, 1))
    body = client.post(f"/api/v1/opportunities/{opp_id}/drafts", json={"kind": "sop_outline"}).json()["body"]
    assert body == "## Motivation\n- OCR work\n- RAG systems"


def test_follow_up_needs_a_first_email_and_reuses_its_thread(client, monkeypatch):
    opp_id = scored_opportunity(client, monkeypatch)
    r = client.post(f"/api/v1/opportunities/{opp_id}/drafts", json={"kind": "follow_up"})
    assert r.status_code == 422 and "first email" in r.json()["detail"]

    first = EmailDraft(subject="PhD Fall 2027 inquiry", body="Dear Prof. Lovelace, first email.", cited_papers=[])
    monkeypatch.setattr(llm, "generate_structured", lambda *a: llm.LLMResult(first, "m", 1, 1))
    client.post(f"/api/v1/opportunities/{opp_id}/drafts", json={"kind": "email"})

    seen = {}

    def fake(system, user, schema, model=None):
        seen["user"] = user
        return llm.LLMResult(EmailDraft(subject="Something else", body="Dear Prof. Lovelace, following up.",
                                        cited_papers=[]), "m", 1, 1)
    monkeypatch.setattr(llm, "generate_structured", fake)
    draft = client.post(f"/api/v1/opportunities/{opp_id}/drafts", json={"kind": "follow_up"}).json()
    assert draft["kind"] == "follow_up" and draft["subject"] == "Re: PhD Fall 2027 inquiry"
    assert "first email." in seen["user"]  # the model sees what was already sent
    assert any("isn't marked as contacted" in w for w in draft["warnings"])
    assert draft["sources"]["first_email_id"]
