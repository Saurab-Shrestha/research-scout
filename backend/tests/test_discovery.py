import pytest
from langgraph.checkpoint.memory import InMemorySaver

from app.db.models import ResearchJob
from app.db.session import SessionLocal
from app.services import discovery, jobs, openalex
from app.services.openalex import Work
from app.workflows.discovery import build_graph
from app.worker import run_job

YEAR = 2026


def inst(id, name, country="US", type="education"):
    return {"id": f"https://openalex.org/{id}", "display_name": name, "country_code": country,
            "type": type, "ror": f"https://ror.org/{id.lower()}"}


def author_raw(id, name, affiliations, works=100, h=30):
    return {"id": f"https://openalex.org/{id}", "display_name": name, "orcid": None, "works_count": works,
            "summary_stats": {"h_index": h}, "affiliations": affiliations}


LSU = inst("I1", "Louisiana State University")
UOFT = inst("I2", "University of Toronto", "CA")
COMPANY = inst("I3", "Wells Fargo", type="company")


def test_primary_institution_prefers_recent_years():
    a = author_raw("A1", "Mark Wilde", [
        {"institution": inst("I9", "Tulane University"), "years": [2005, 2003]},
        {"institution": LSU, "years": [2025, 2024, 2023]},
    ])
    chosen, _ = discovery.primary_institution(a, ["US", "CA"], YEAR)
    assert chosen["display_name"] == "Louisiana State University"


def test_primary_institution_refuses_ties():
    a = author_raw("A1", "X", [{"institution": LSU, "years": [2025]}, {"institution": UOFT, "years": [2025]}])
    chosen, note = discovery.primary_institution(a, ["US", "CA"], YEAR)
    assert chosen is None and "ambiguous" in note


def test_select_candidates_filters_industry_juniors_and_other_countries():
    authors = [
        author_raw("A1", "Prof", [{"institution": UOFT, "years": [2025]}]),
        author_raw("A2", "Industry", [{"institution": COMPANY, "years": [2025]}]),
        author_raw("A3", "Student", [{"institution": LSU, "years": [2025]}], works=8, h=3),
        author_raw("A4", "Abroad", [{"institution": inst("I5", "ETH", "CH"), "years": [2025]}]),
    ]
    kept, skipped = discovery.select_candidates(authors, {"A1": 5}, ["US", "CA"], YEAR, 10)
    assert [c.name for c in kept] == ["Prof"]
    assert len(skipped) == 3


def test_topic_queries_expand_areas_and_dedupe():
    assert discovery.topic_queries(["quantum_computing", "quantum_computing"], "quantum error correction") == [
        "quantum computing", "quantum information", "quantum error correction"]


@pytest.fixture
def fake_openalex(monkeypatch):
    calls = {"works": 0}
    monkeypatch.setattr(openalex, "search_topics", lambda q, limit: [{"id": "T10682", "name": "Quantum Computing"}])

    def top_authors(topics, countries, from_year, limit, institution_ids=None):
        calls["institution_ids"] = institution_ids
        return [{"id": "A1", "name": "Prof One", "topic_works": 40}, {"id": "A2", "name": "Prof Two", "topic_works": 20}]
    monkeypatch.setattr(openalex, "top_authors_for_topics", top_authors)
    monkeypatch.setattr(openalex, "get_authors", lambda ids: [
        author_raw("A1", "Prof One", [{"institution": UOFT, "years": [2025]}]),
        author_raw("A2", "Prof Two", [{"institution": LSU, "years": [2026]}]),
    ])

    def recent_works(author_id, from_year, limit):
        calls["works"] += 1
        return [Work(f"W{author_id}", None, None, f"Paper by {author_id}", None, 2025, None, None, "last")]
    monkeypatch.setattr(openalex, "recent_works", recent_works)
    return calls


def make_job(**inputs) -> ResearchJob:
    with SessionLocal() as db:
        job = ResearchJob(job_type="discovery", input_json={
            "query": None, "countries": ["US", "CA"], "research_areas": ["quantum_computing"],
            "max_results": 10, "find_pages": False} | inputs, status="running", attempts=1)
        db.add(job)
        db.commit()
        return job


def test_discovery_job_creates_professors_with_publications(client, fake_openalex):
    job = make_job()
    assert run_job(build_graph(InMemorySaver()), job.id) == "completed"

    result = client.get(f"/api/v1/research-jobs/{job.id}").json()
    assert result["status"] == "completed"
    assert result["result"]["professors"] == 2 and result["result"]["new_professors"] == 2
    profs = client.get("/api/v1/professors").json()
    assert {p["name"] for p in profs} == {"Prof One", "Prof Two"}
    detail = client.get(f"/api/v1/professors/{profs[0]['id']}").json()
    assert len(detail["publications"]) == 1
    events = [e["event_type"] for e in client.get(f"/api/v1/research-jobs/{job.id}/events").json()]
    assert events[0] == "started" and events[-1] == "completed"


def test_rerunning_discovery_skips_saved_researchers(client, fake_openalex):
    graph = build_graph(InMemorySaver())
    run_job(graph, make_job().id)
    again = make_job()
    run_job(graph, again.id)
    assert len(client.get("/api/v1/professors").json()) == 2
    assert client.get(f"/api/v1/research-jobs/{again.id}").json()["result"]["professors"] == 0
    assert fake_openalex["works"] == 2


def test_refresh_includes_saved_researchers_and_relinks_papers(client, fake_openalex):
    graph = build_graph(InMemorySaver())
    run_job(graph, make_job().id)
    again = make_job(refresh=True)
    run_job(graph, again.id)
    result = client.get(f"/api/v1/research-jobs/{again.id}").json()["result"]
    assert result["professors"] == 2 and result["new_professors"] == 0
    assert len(client.get("/api/v1/professors").json()) == 2
    assert fake_openalex["works"] == 4


def test_select_candidates_skips_known_ids_and_split_profiles():
    authors = [
        author_raw("A1", "Saved", [{"institution": UOFT, "years": [2025]}]),
        author_raw("A9", "Roger B. Grosse", [{"institution": UOFT, "years": [2025]}]),  # second OpenAlex ID, same person
        author_raw("A3", "New", [{"institution": UOFT, "years": [2025]}]),
    ]
    known = {"A1", (("roger", "grosse"), "I2")}
    kept, skipped = discovery.select_candidates(authors, {}, ["US", "CA"], YEAR, 10, known)
    assert [c.name for c in kept] == ["New"]
    assert all(s["reason"].startswith("already") for s in skipped)


def test_failed_job_resumes_from_checkpoint(client, fake_openalex, monkeypatch):
    graph = build_graph(InMemorySaver())
    job = make_job()
    discovered = {"n": 0}
    real_top = openalex.top_authors_for_topics

    def counting_top(*a, **k):
        discovered["n"] += 1
        return real_top(*a, **k)
    monkeypatch.setattr(openalex, "top_authors_for_topics", counting_top)

    def boom(*a, **k):
        raise openalex.ScholarlyError("budget exhausted")
    monkeypatch.setattr(openalex, "get_authors", boom)
    assert run_job(graph, job.id) == "queued"  # retryable

    monkeypatch.undo()
    fake_openalex_authors = [author_raw("A1", "Prof One", [{"institution": UOFT, "years": [2025]}])]
    monkeypatch.setattr(openalex, "get_authors", lambda ids: fake_openalex_authors)
    monkeypatch.setattr(openalex, "top_authors_for_topics", counting_top)
    monkeypatch.setattr(openalex, "recent_works", lambda *a, **k: [])
    assert run_job(graph, job.id) == "completed"
    assert discovered["n"] == 1  # discover_authors did not run again
    events = [e["event_type"] for e in client.get(f"/api/v1/research-jobs/{job.id}/events").json()]
    assert "resumed" in events


def test_job_fails_after_max_attempts():
    job = make_job()
    with SessionLocal() as db:
        db.get(ResearchJob, job.id).attempts = jobs.MAX_ATTEMPTS
        db.commit()
    assert jobs.fail(job.id, "boom") == "failed"


def test_claim_next_takes_oldest_queued():
    with SessionLocal() as db:
        db.add_all([ResearchJob(job_type="discovery", input_json={}), ResearchJob(job_type="discovery", input_json={})])
        db.commit()
        first, second, third = jobs.claim_next(db), jobs.claim_next(db), jobs.claim_next(db)
    assert first and second and first != second and third is None


def test_create_job_is_idempotent(client):
    body = {"research_areas": ["quantum_computing"], "max_results": 5}
    first = client.post("/api/v1/research-jobs", json=body, headers={"Idempotency-Key": "k1"})
    second = client.post("/api/v1/research-jobs", json=body, headers={"Idempotency-Key": "k1"})
    assert first.status_code == 202 and second.status_code == 200
    assert first.json()["id"] == second.json()["id"]


def test_create_job_requires_topic(client):
    assert client.post("/api/v1/research-jobs", json={}).status_code == 422


def test_primary_institution_must_agree_with_last_known():
    a = author_raw("A1", "Visiting coauthor", [{"institution": LSU, "years": [2025, 2024]}])
    a["last_known_institutions"] = [inst("I7", "NIMS", "JP", "facility")]
    chosen, note = discovery.primary_institution(a, ["US", "CA"], YEAR)
    assert chosen is None and "last known" in note


CANDIDATES = {
    "quantum computing": [{"id": "T1", "name": "Quantum Computing Algorithms"},
                          {"id": "T2", "name": "Quantum and electron transport phenomena"}],
    "quantum information": [{"id": "T3", "name": "Quantum Information and Cryptography"}],
}


def fake_planner(monkeypatch, selected=None, error=None):
    from app.services import llm

    def fake(system, user, schema, model=None):
        if error:
            raise llm.LLMError(error)
        return llm.LLMResult(schema(selected=[{"topic_id": t, "reason": "r"} for t in selected]), model, 1, 1)
    monkeypatch.setattr(llm, "generate_structured", fake)


def test_planner_picks_subset_and_ignores_invented_ids(monkeypatch):
    fake_planner(monkeypatch, selected=["T1", "T3", "T999"])
    chosen, method = discovery.choose_topics(["quantum_computing"], None, CANDIDATES)
    assert [c["id"] for c in chosen] == ["T1", "T3"]
    assert method.startswith("topic-planner")


def test_planner_failure_falls_back_to_best_match_per_query(monkeypatch):
    fake_planner(monkeypatch, error="quota")
    chosen, method = discovery.choose_topics(["quantum_computing"], None, CANDIDATES)
    assert [c["id"] for c in chosen] == ["T1", "T3"]
    assert method.startswith("fallback")


def test_planner_choosing_nothing_falls_back(monkeypatch):
    fake_planner(monkeypatch, selected=["T999"])
    chosen, method = discovery.choose_topics(["quantum_computing"], None, CANDIDATES)
    assert [c["id"] for c in chosen] == ["T1", "T3"] and "nothing" in method


def test_university_search_keeps_only_researchers_based_there(client, fake_openalex):
    job = make_job(institutions=[{"id": "I2", "name": "University of Toronto", "country": "CA"}])
    run_job(build_graph(InMemorySaver()), job.id)
    assert fake_openalex["institution_ids"] == ["I2"]
    assert [p["name"] for p in client.get("/api/v1/professors").json()] == ["Prof One"]  # Prof Two is at LSU


def test_university_search_endpoint_and_countries_follow_universities(client, monkeypatch):
    monkeypatch.setattr(openalex, "search_institutions", lambda q, countries: [
        {"id": "I2", "name": "University of Toronto", "country": "CA", "city": "Toronto"},
        {"id": "I7", "name": "Somewhere Else", "country": "BR", "city": None}])
    assert [i["id"] for i in client.get("/api/v1/research-jobs/institutions?q=toronto").json()] == ["I2"]
    job = client.post("/api/v1/research-jobs", json={"research_areas": ["quantum_computing"], "countries": ["US"],
                                                     "institutions": [{"id": "I2", "name": "UofT", "country": "CA"}]}).json()
    assert job["input"]["countries"] == ["CA"]
    bad = client.post("/api/v1/research-jobs", json={"research_areas": ["x"], "institutions": [{"id": "x", "name": "n", "country": "CA"}]})
    assert bad.status_code == 422
