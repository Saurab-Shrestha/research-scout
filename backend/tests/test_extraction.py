from app.schemas.extraction import Claim, PageExtraction
from app.services import llm

PAGE = """Jane Doe, Associate Professor
Department of Computer Science, University of Example
Email: jdoe@cs.example.edu
Research: quantum machine learning; variational algorithms.
I am recruiting PhD students for Fall 2027."""


def claim(value=None, quote=None):
    return Claim(value=value, evidence_quote=quote)


def fake_extraction(**overrides) -> PageExtraction:
    fields = dict(
        page_kind="faculty_profile",
        university=claim("University of Example", "University of Example"),
        department=claim("Department of Computer Science", "Department of Computer Science"),
        professor_name=claim("Jane Doe", "Jane Doe, Associate Professor"),
        professor_title=claim("Associate Professor", "Associate Professor"),
        institutional_email=claim("jdoe@cs.example.edu", "Email: jdoe@cs.example.edu"),
        accepting_students=claim("yes", "I am recruiting PhD students"),
        research_topics=[claim("quantum machine learning", "quantum machine learning"),
                         claim("tensor networks", "tensor networks")],  # not on page
        degree_types=[claim("phd", "PhD students")],
        eligibility_requirements=[],
        funding_details=[claim("fully funded", "fully funded with stipend")],  # fabricated quote
        application_deadline=claim(),
        application_url=claim(),
        warnings=[],
    )
    return PageExtraction(**(fields | overrides))


def use_fake_llm(monkeypatch, extraction: PageExtraction):
    def fake(system, user, schema, model):
        assert "<page_content>" in user
        return llm.LLMResult(parsed=extraction, model=model, input_tokens=100, output_tokens=50)
    monkeypatch.setattr(llm, "generate_structured", fake)


def ingest(client, text, source_type="web_page"):
    # Text ingestion stores content without fetching; mark as web_page to simulate a fetched profile.
    body = client.post("/api/v1/sources/ingest", json={"text": text, "source_type": source_type}).json()
    if source_type == "web_page":
        from app.db.models import Source
        from app.db.session import SessionLocal
        with SessionLocal() as db:
            db.get(Source, body["source_id"]).source_type = "web_page"
            db.commit()
    return body["source_id"]


def test_extract_creates_professor_with_verified_evidence_only(client, monkeypatch):
    use_fake_llm(monkeypatch, fake_extraction())
    source_id = ingest(client, PAGE)

    result = client.post(f"/api/v1/sources/{source_id}/extract").json()
    assert result["professor_id"]
    assert result["unverified_fields"] == 2  # tensor networks + fabricated funding quote

    prof = client.get(f"/api/v1/professors/{result['professor_id']}").json()
    assert prof["email"] == "jdoe@cs.example.edu"
    assert prof["accepting_students"] is True
    assert prof["research_summary"] == "quantum machine learning"  # unsupported topic excluded
    statuses = {e["field_name"]: e["verification_status"] for e in prof["evidence"] if e["field_name"] == "funding_details"}
    assert statuses == {"funding_details": "quote_not_found"}


def test_rerun_extraction_is_idempotent(client, monkeypatch):
    use_fake_llm(monkeypatch, fake_extraction())
    source_id = ingest(client, PAGE)

    first = client.post(f"/api/v1/sources/{source_id}/extract").json()
    second = client.post(f"/api/v1/sources/{source_id}/extract").json()
    assert first["professor_id"] == second["professor_id"]
    assert len(client.get("/api/v1/professors").json()) == 1
    evidence = client.get(f"/api/v1/professors/{first['professor_id']}").json()["evidence"]
    assert len(evidence) == first["verified_fields"] + first["unverified_fields"]


def test_social_post_never_creates_professor(client, monkeypatch):
    use_fake_llm(monkeypatch, fake_extraction(page_kind="social_post"))
    source_id = ingest(client, PAGE, source_type="social_post")

    result = client.post(f"/api/v1/sources/{source_id}/extract").json()
    assert result["professor_id"] is None
    assert client.get("/api/v1/professors").json() == []


def test_unverified_name_does_not_create_professor(client, monkeypatch):
    use_fake_llm(monkeypatch, fake_extraction(professor_name=claim("John Smith", "John Smith")))
    source_id = ingest(client, PAGE)
    assert client.post(f"/api/v1/sources/{source_id}/extract").json()["professor_id"] is None
