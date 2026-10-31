from datetime import date

from langgraph.checkpoint.memory import InMemorySaver

from app.db.models import (CandidateProfile, FundingAssessment, MatchResult, Professor, ProfessorPublication,
                           Program, Publication, ResearchJob, University)
from app.db.session import SessionLocal
from app.schemas.extraction import Claim
from app.schemas.program import EnglishRequirement, ProgramExtraction
from app.services import eligibility, ingestion, llm, matching
from app.services.fetcher import FetchResult
from app.services.programs import classify_funding
from app.worker import run_job
from app.workflows import evaluation

TODAY = date(2026, 10, 29)
PROFILE = {"education": [{"degree": "BSc", "gpa": 80, "gpa_scale": 100}],
           "test_scores": [{"test": "PTE Academic", "score": "77"}]}


# --- Funding classification -----------------------------------------------------------------

def test_guarantee_with_full_tuition_and_stipend_is_confirmed_full():
    f = classify_funding("US", "phd", {"guaranteed_funding": "yes", "tuition_coverage": "full",
                                        "stipend_amount": "45,000", "stipend_currency": "USD"}, [], [], False)
    assert f["funding_status"] == "confirmed_full" and f["stipend_amount"] == 45000 and f["counts_for_visa_proof"]


def test_stipend_without_guarantee_is_partial_and_explains_gap():
    f = classify_funding("CA", "thesis_masters", {"stipend_amount": "24000"}, ["research assistantship"], [], False)
    assert f["funding_status"] == "confirmed_partial" and f["basis"] == "research_assistantship"
    assert "guarantee" in f["explanation"]


def test_no_evidence_uses_country_defaults():
    assert classify_funding("US", "course_masters", {}, [], [], False)["funding_status"] == "unfunded"
    assert classify_funding("CA", "thesis_masters", {}, [], [], False)["basis"] == "supervisor"


def test_unverified_quotes_are_never_confirmed():
    assert classify_funding("US", "phd", {}, [], [], True)["funding_status"] == "advertised_unverified"


def test_funding_closed_to_internationals_cannot_be_visa_proof():
    f = classify_funding("US", "phd", {"guaranteed_funding": "yes", "tuition_coverage": "full", "stipend_amount": "1",
                                        "funding_for_international_students": "no"}, [], [], False)
    assert f["international_eligible"] is False and f["counts_for_visa_proof"] is False


# --- Eligibility ----------------------------------------------------------------------------

def test_pte_meets_stated_minimum():
    status, checks = eligibility.evaluate(PROFILE, {"english": [{"test": "PTE Academic", "minimum": "65"}]},
                                          "US", "phd", date(2026, 12, 15), TODAY)
    assert {c["name"]: c["status"] for c in checks}["english"] == "ok"
    assert status == "potentially_eligible"  # GPA still needs evaluation


def test_pte_not_accepted_is_ineligible():
    status, _ = eligibility.evaluate(PROFILE, {"pte_accepted": "no"}, "US", "phd", None, TODAY)
    assert status == "ineligible"


def test_program_closed_to_internationals_is_ineligible():
    status, checks = eligibility.evaluate(PROFILE, {"international_applicants_accepted": "no"}, "CA",
                                          "thesis_masters", None, TODAY)
    assert status == "ineligible"
    assert {c["name"]: c["status"] for c in checks}["international"] == "fail"


def test_passed_deadline_is_ineligible():
    status, checks = eligibility.evaluate(PROFILE, {}, "US", "phd", date(2026, 10, 1), TODAY)
    assert status == "ineligible" and "passed" in checks[-1]["detail"]


def test_canadian_phd_from_bachelors_is_a_warning():
    _, checks = eligibility.evaluate(PROFILE, {}, "CA", "phd", None, TODAY)
    assert checks[0]["status"] == "warn"


def test_percentage_grade_is_unknown_not_pass():
    _, checks = eligibility.evaluate(PROFILE, {"minimum_gpa": "3.0/4.0"}, "US", "phd", None, TODAY)
    assert {c["name"]: c["status"] for c in checks}["gpa"] == "unknown"


def test_mostly_unknown_is_insufficient_information():
    status, _ = eligibility.evaluate({"education": [], "test_scores": []}, {}, "US", "phd", None, TODAY)
    assert status == "insufficient_information"


# --- Scoring ---------------------------------------------------------------------------------

def test_timing_and_overall_formula():
    assert matching.timing_score(None, TODAY) == 50
    assert matching.timing_score(date(2026, 10, 1), TODAY) == 0
    assert matching.timing_score(date(2027, 1, 1), TODAY) == 100
    assert matching.overall({"research": 100, "funding": 100, "eligibility": 100, "availability": 100, "timing": 100}) == 100


def test_unfunded_is_excluded_when_funding_needed():
    f = FundingAssessment(funding_status="unfunded", timing="unknown", international_eligible=None)
    assert matching.exclusion_reason("eligible", f, {"needs_tuition_coverage": True}) == "unfunded"


# --- End to end: evaluation job with fake web + LLM ------------------------------------------

def claim(v=None, q=None):
    return Claim(value=v, evidence_quote=q)


ADMISSIONS = ("Graduate Admissions, Example University. All admitted PhD students receive full funding, "
              "including full tuition and a stipend of $45,000 per year. Deadline: December 15, 2026. "
              "PTE Academic minimum 68.")


def program_extraction() -> ProgramExtraction:
    return ProgramExtraction(
        page_kind="admissions_page", university=claim("Example University", "Example University"),
        program_name=claim("PhD in Computer Science", None), degree_types=[claim("phd", "PhD")],
        guaranteed_funding=claim("yes", "All admitted PhD students receive full funding"),
        tuition_coverage=claim("full", "full tuition"), stipend_amount=claim("45000", "a stipend of $45,000 per year"),
        stipend_currency=claim("USD", "$45,000"), stipend_period=claim("year", "per year"),
        funding_duration_years=claim(), funding_sources=[], funding_for_international_students=claim(),
        funding_conditions=[], application_deadline=claim("2026-12-15", "Deadline: December 15, 2026"),
        deadline_term=claim(), english_tests=[EnglishRequirement(test="PTE Academic", minimum="68",
                                                                  evidence_quote="PTE Academic minimum 68")],
        pte_accepted=claim("yes", "PTE Academic"), international_applicants_accepted=claim(), minimum_gpa=claim(), requires_masters_for_phd=claim(),
        supervisor_required_before_admission=claim(), prerequisites=[], warnings=[],
    )


def seed():
    with SessionLocal() as db:
        db.add(CandidateProfile(name="Me", education_json=PROFILE["education"], test_scores_json=PROFILE["test_scores"],
                                research_interests=["quantum machine learning"], intended_start_term="Fall 2027",
                                funding_preferences_json={"needs_tuition_coverage": True}))
        uni = University(name="Example University", normalized_name="example university", country="US", aliases=[])
        db.add(uni)
        db.flush()
        prof = Professor(name="Ada Lovelace", university_id=uni.id, faculty_url="https://cs.example.edu/ada",
                         accepting_students=True)
        pub = Publication(openalex_id="W1", title="Quantum machine learning", publication_year=2026)
        db.add_all([prof, pub])
        db.flush()
        db.add(ProfessorPublication(professor_id=prof.id, publication_id=pub.id, author_position="last"))
        db.commit()
        return prof.id


def test_evaluation_job_verifies_program_and_ranks(client, monkeypatch):
    prof_id = seed()
    monkeypatch.setattr(llm, "search_text", lambda prompt, model: ("https://grad.example.edu/phd", []))
    monkeypatch.setattr(ingestion, "fetch_public_page", lambda url: FetchResult(url, 200, "text/plain", ADMISSIONS))
    monkeypatch.setattr(llm, "generate_structured", lambda *a: llm.LLMResult(program_extraction(), "m", 1, 1))
    monkeypatch.setattr(llm, "embed", lambda texts: [[1.0, 0.0] for _ in texts])

    with SessionLocal() as db:
        job = ResearchJob(job_type="evaluation", status="running", attempts=1,
                          input_json={"professor_ids": [str(prof_id)], "degree_types": ["phd"]})
        db.add(job)
        db.commit()
    assert run_job({"evaluation": evaluation.build_graph(InMemorySaver())}, job.id) == "completed"

    ranked = client.get("/api/v1/opportunities").json()
    assert len(ranked) == 1
    opp = ranked[0]
    assert opp["funding_status"] == "confirmed_full"
    assert opp["deadline"] == "2026-12-15"
    assert opp["stipend"] == "USD 45,000/year"
    english = next(c for c in opp["explanation"]["eligibility_checks"] if c["name"] == "english")
    assert english["status"] == "ok"
    assert opp["scores"]["research"] == 100  # identical fake embeddings

    detail = client.get(f"/api/v1/opportunities/{opp['id']}").json()
    assert any(e["field"] == "guaranteed_funding" and e["status"] == "quote_verified" for e in detail["program_evidence"])

    # Second run reuses the fresh program: no new search, no duplicates
    monkeypatch.setattr(llm, "search_text", lambda *a: (_ for _ in ()).throw(AssertionError("searched again")))
    with SessionLocal() as db:
        job2 = ResearchJob(job_type="evaluation", status="running", attempts=1,
                           input_json={"professor_ids": [str(prof_id)], "degree_types": ["phd"]})
        db.add(job2)
        db.commit()
    run_job({"evaluation": evaluation.build_graph(InMemorySaver())}, job2.id)
    with SessionLocal() as db:
        assert db.query(Program).count() == 1 and db.query(MatchResult).count() == 1


def test_evaluate_requires_profile(client):
    assert client.post("/api/v1/opportunities/evaluate", json={}).status_code == 422


def test_reverify_with_new_program_name_keeps_one_opportunity(client, monkeypatch):
    prof_id = seed()
    monkeypatch.setattr(ingestion, "fetch_public_page", lambda url: FetchResult(url, 200, "text/plain", ADMISSIONS))
    monkeypatch.setattr(llm, "embed", lambda texts: [[1.0, 0.0] for _ in texts])
    for i, name in enumerate(["PhD in Computer Science", "Doctor of Philosophy (PhD)"]):
        ex = program_extraction()
        ex.program_name = claim(name, "Graduate Admissions")
        monkeypatch.setattr(llm, "search_text", lambda prompt, model, i=i: (f"https://grad.example.edu/phd{i}", []))
        monkeypatch.setattr(llm, "generate_structured", lambda *a, ex=ex: llm.LLMResult(ex, "m", 1, 1))
        with SessionLocal() as db:
            job = ResearchJob(job_type="evaluation", status="running", attempts=1,
                              input_json={"professor_ids": [str(prof_id)], "degree_types": ["phd"], "force": True})
            db.add(job)
            db.commit()
        run_job({"evaluation": evaluation.build_graph(InMemorySaver())}, job.id)
    ranked = client.get("/api/v1/opportunities").json()
    assert len(ranked) == 1 and ranked[0]["program"] == "Doctor of Philosophy (PhD)"


def test_network_errors_become_llm_errors(monkeypatch):
    import httpx
    import pytest

    class Boom:
        class models:
            @staticmethod
            def generate_content(**kwargs):
                raise httpx.RemoteProtocolError("Server disconnected")
    monkeypatch.setattr(llm, "_client", lambda: Boom)
    with pytest.raises(llm.LLMError, match="RemoteProtocolError"):
        llm.search_text("q", "m")


def test_rerun_quoting_less_keeps_earlier_verified_funding(client, monkeypatch):
    prof_id = seed()
    monkeypatch.setattr(llm, "search_text", lambda prompt, model: ("https://grad.example.edu/phd", []))
    monkeypatch.setattr(ingestion, "fetch_public_page", lambda url: FetchResult(url, 200, "text/plain", ADMISSIONS))
    monkeypatch.setattr(llm, "embed", lambda texts: [[1.0, 0.0] for _ in texts])

    def run(ex):
        monkeypatch.setattr(llm, "generate_structured", lambda *a: llm.LLMResult(ex, "m", 1, 1))
        with SessionLocal() as db:
            job = ResearchJob(job_type="evaluation", status="running", attempts=1,
                              input_json={"professor_ids": [str(prof_id)], "degree_types": ["phd"], "force": True})
            db.add(job)
            db.commit()
        run_job({"evaluation": evaluation.build_graph(InMemorySaver())}, job.id)

    run(program_extraction())
    # Second run on a different page quotes only the stipend, not the guarantee or tuition
    monkeypatch.setattr(llm, "search_text", lambda prompt, model: ("https://grad.example.edu/other", []))
    weaker = program_extraction()
    weaker.guaranteed_funding, weaker.tuition_coverage = claim(), claim()
    run(weaker)
    assert client.get("/api/v1/opportunities").json()[0]["funding_status"] == "confirmed_full"


def test_parallel_run_covers_every_university_and_caches_default_only(client, monkeypatch):
    prof_id = seed()
    with SessionLocal() as db:
        other = University(name="Other University", normalized_name="other university", country="US", aliases=[])
        db.add(other)
        db.flush()
        prof2 = Professor(name="Alan Turing", university_id=other.id)
        db.add(prof2)
        db.commit()
        ids = [str(prof_id), str(prof2.id)]
    searches = []
    monkeypatch.setattr(llm, "search_text", lambda prompt, model: (searches.append(prompt), ("no pages found", []))[1])
    monkeypatch.setattr(llm, "embed", lambda texts: [[1.0, 0.0] for _ in texts])

    def run():
        with SessionLocal() as db:
            job = ResearchJob(job_type="evaluation", status="running", attempts=1,
                              input_json={"professor_ids": ids, "degree_types": ["phd", "thesis_masters"]})
            db.add(job)
            db.commit()
        return run_job({"evaluation": evaluation.build_graph(InMemorySaver())}, job.id)

    assert run() == "completed"
    assert len(searches) == 8  # 2 professors × 2 degrees, each retried once on an empty answer
    with SessionLocal() as db:
        assert db.query(Program).count() == 4
    run()
    assert len(searches) == 8  # default-only results are reused for a day, not searched again


def test_llm_client_is_shared_across_threads(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    import time
    llm._make_client.cache_clear()
    monkeypatch.setattr(llm.genai, "Client", lambda **kw: (time.sleep(0.05), object())[1])
    with ThreadPoolExecutor(8) as pool:
        clients = list(pool.map(lambda _: llm._client(), range(8)))
    llm._make_client.cache_clear()
    assert len({id(c) for c in clients}) == 1


def test_worker_records_llm_usage_and_cost(monkeypatch):
    from types import SimpleNamespace
    from app.core.config import settings
    monkeypatch.setattr(settings, "llm_usd_per_million_input", 1.0)
    monkeypatch.setattr(settings, "llm_usd_per_million_output", 2.0)
    monkeypatch.setattr(settings, "grounded_search_usd_each", 0.01)

    class FakeGraph:
        def get_state(self, config):
            return SimpleNamespace(next=())

        def invoke(self, state, config):
            llm._meter(SimpleNamespace(usage_metadata=SimpleNamespace(prompt_token_count=1_000_000,
                                                                     candidates_token_count=500_000)), searches=3)
            return {"result_summary": {}}

    with SessionLocal() as db:
        job = ResearchJob(job_type="evaluation", status="running", attempts=1, input_json={})
        db.add(job)
        db.commit()
    assert run_job(FakeGraph(), job.id) == "completed"
    with SessionLocal() as db:
        job = db.get(ResearchJob, job.id)
        assert job.tokens_used == 1_500_000 and job.cost_usd == 2.03


def test_country_systems_drive_defaults_and_phd_entry():
    from app.services.programs import classify_funding
    germany = classify_funding("DE", "phd", {}, [], [], False)
    assert (germany["funding_status"], germany["basis"]) == ("potential", "supervisor")
    assert classify_funding("DE", "thesis_masters", {}, [], [], False)["funding_status"] == "unfunded"
    assert classify_funding("XX", "phd", {}, [], [], False)["funding_status"] == "unknown"
    _, checks = eligibility.evaluate(PROFILE, {}, "JP", "phd", None, TODAY)
    assert next(c for c in checks if c["name"] == "degree")["status"] == "warn"


def test_studying_in_the_program_country_makes_you_domestic():
    profile = {"education": [{"degree": "BSc", "country": "DE"}], "test_scores": []}
    assert not eligibility.is_international(profile, "DE")
    assert eligibility.is_international(profile, "GB")
