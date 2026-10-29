from app.db.models import Professor, University
from app.db.session import SessionLocal
from app.services import openalex
from app.services.openalex import AuthorCandidate, Work
from app.services.publications import choose_author

UOFT = "I185261750"


def author(id, name, works, institutions=(UOFT,)):
    return AuthorCandidate(id, name, None, works, list(institutions), f"https://api.openalex.org/authors/{id}", {"id": id})


def test_unique_match_at_current_institution_resolves():
    chosen, conf, _ = choose_author([author("A1", "Roger B. Grosse", 117)], "Roger Grosse", UOFT)
    assert chosen.openalex_id == "A1" and conf == 0.9


def test_dominant_profile_beats_small_fragments():
    chosen, _, _ = choose_author([author("A1", "Jane Doe", 200), author("A2", "Jane Doe", 3)], "Jane Doe", UOFT)
    assert chosen.openalex_id == "A1"


def test_two_similar_profiles_are_ambiguous():
    chosen, _, reason = choose_author([author("A1", "Wei Zhang", 80), author("A2", "Wei Zhang", 60)], "Wei Zhang", UOFT)
    assert chosen is None and "plausible" in reason


def test_name_only_match_needs_review():
    chosen, _, _ = choose_author([author("A1", "Jane Doe", 50, institutions=("I999",))], "Jane Doe", UOFT)
    assert chosen is None


def test_different_name_never_matches():
    chosen, _, _ = choose_author([author("A1", "Jane Smith", 50)], "Jane Doe", UOFT)
    assert chosen is None


def seed_professor() -> str:
    with SessionLocal() as db:
        uni = University(name="University of Toronto", normalized_name="university of toronto",
                         country="CA", openalex_id=UOFT)
        db.add(uni)
        db.flush()
        prof = Professor(name="Roger Grosse", university_id=uni.id, faculty_url="https://www.cs.toronto.edu/~rgrosse")
        db.add(prof)
        db.commit()
        return str(prof.id)


def test_refresh_links_publications_idempotently(client, monkeypatch):
    monkeypatch.setattr(openalex, "search_authors", lambda name, inst, orcid: [author("A5067036768", "Roger Grosse", 117)])
    monkeypatch.setattr(openalex, "recent_works", lambda author_id, from_year, limit: [
        Work("W1", "10.1/x", "2602.10568", "Gauss-Newton Unlearning", "abstract", 2026,
             "https://doi.org/10.1/x", "https://arxiv.org/pdf/2602.10568", "last"),
        Work("W2", None, None, "Another paper", None, 2025, None, None, "middle"),
    ])
    prof_id = seed_professor()

    first = client.post(f"/api/v1/professors/{prof_id}/refresh").json()
    second = client.post(f"/api/v1/professors/{prof_id}/refresh").json()
    assert first["status"] == second["status"] == "resolved"

    prof = client.get(f"/api/v1/professors/{prof_id}").json()
    assert prof["openalex_id"] == "A5067036768"
    assert [p["title"] for p in prof["publications"]] == ["Gauss-Newton Unlearning", "Another paper"]
    assert [e["field_name"] for e in prof["evidence"]] == ["openalex_id"]  # replaced, not duplicated


def test_refresh_reports_ambiguity_without_linking(client, monkeypatch):
    monkeypatch.setattr(openalex, "search_authors", lambda name, inst, orcid: [
        author("A1", "Roger Grosse", 50), author("A2", "Roger Grosse", 40)])
    prof_id = seed_professor()

    result = client.post(f"/api/v1/professors/{prof_id}/refresh").json()
    assert result["status"] == "unresolved" and len(result["candidates"]) == 2
    assert client.get(f"/api/v1/professors/{prof_id}").json()["openalex_id"] is None
