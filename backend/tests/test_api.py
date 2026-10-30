from app.services import ingestion
from app.services.fetcher import FetchResult

PROFILE = {
    "name": "Test Candidate",
    "education": [{"degree": "BE", "field": "Computer Engineering", "university": "Example University",
                   "gpa": 3.7, "gpa_scale": 4.0, "relevant_courses": ["Linear Algebra"]}],
    "research_interests": ["quantum machine learning"],
    "funding_preferences": {"requires_funding_at_admission": True},
}


def test_health(client):
    assert client.get("/api/v1/health").json() == {"status": "ok", "database": "ok"}


def test_profile_roundtrip(client):
    assert client.get("/api/v1/profile").status_code == 404

    created = client.put("/api/v1/profile", json=PROFILE).json()
    updated = client.put("/api/v1/profile", json={**PROFILE, "skills": ["PyTorch"]}).json()

    assert updated["id"] == created["id"]  # single profile, updated in place
    fetched = client.get("/api/v1/profile").json()
    assert fetched["skills"] == ["PyTorch"]
    assert fetched["education"][0]["gpa_scale"] == 4.0


def test_ingest_requires_url_or_text(client):
    assert client.post("/api/v1/sources/ingest", json={}).status_code == 422


def test_ingest_text_is_idempotent(client):
    post = {"text": "Prof. X is hiring 2 funded PhD students in quantum ML.",
            "url": "https://www.linkedin.com/posts/abc?utm_source=share"}
    first = client.post("/api/v1/sources/ingest", json=post).json()
    second = client.post("/api/v1/sources/ingest", json=post).json()

    assert first["created"] is True and second["created"] is False
    assert first["source_id"] == second["source_id"]
    assert first["canonical_url"] == "https://www.linkedin.com/posts/abc"


def test_ingest_text_without_url(client):
    body = client.post("/api/v1/sources/ingest", json={"text": "Funded MSc opening"}).json()
    assert body["canonical_url"].startswith("urn:sha256:")


def test_ingest_url_is_idempotent(client, monkeypatch):
    page = FetchResult("https://uni.example.edu/jane", 200, "text/html",
                       "<html><body><article><h1>Prof Jane</h1><p>Quantum algorithms research.</p></article></body></html>")
    monkeypatch.setattr(ingestion, "fetch_public_page", lambda url: page)

    first = client.post("/api/v1/sources/ingest", json={"url": "https://uni.example.edu/jane/"}).json()
    second = client.post("/api/v1/sources/ingest", json={"url": "https://uni.example.edu/jane"}).json()
    assert first["source_id"] == second["source_id"]
    assert second["created"] is False


def test_ingest_rejects_private_url(client):
    response = client.post("/api/v1/sources/ingest", json={"url": "http://127.0.0.1/admin"})
    assert response.status_code == 400


def test_web_app_served_with_spa_fallback(client, tmp_path, monkeypatch):
    from app import main
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<div id=root></div>")
    (tmp_path / "assets" / "app.js").write_text("console.log(1)")
    monkeypatch.setattr(main, "WEB_DIST", tmp_path)
    assert client.get("/tracker").text == "<div id=root></div>"
    assert client.get("/assets/app.js").text == "console.log(1)"
    assert client.get("/api/v1/nope").status_code == 404
    assert client.get("/..%2F..%2Fetc%2Fpasswd").text == "<div id=root></div>"
