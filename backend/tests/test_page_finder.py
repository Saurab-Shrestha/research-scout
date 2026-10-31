from app.db.models import Professor, University
from app.db.session import SessionLocal
from app.schemas.extraction import Claim, PageExtraction
from app.services import ingestion, llm, page_finder
from app.services.fetcher import FetchResult

PAGES = {
    "https://sites.usc.edu/zhuang": "Quntao Zhuang\nAssistant Professor\nUniversity of Southern California\nQuantum sensing and networks.",
    "https://other.edu/qz": "Q. Zhuang\nUniversity of Elsewhere\nQuantum sensing.",
}


def claim(value=None, quote=None):
    return Claim(value=value, evidence_quote=quote)


def page_extraction(name: str, university: str) -> PageExtraction:
    return PageExtraction(
        page_kind="faculty_profile", university=claim(university, university), department=claim(),
        professor_name=claim(name, name), professor_title=claim("Assistant Professor", "Assistant Professor"),
        institutional_email=claim(), accepting_students=claim(), research_topics=[], degree_types=[],
        eligibility_requirements=[], funding_details=[], application_deadline=claim(), application_url=claim(),
        warnings=[],
    )


def setup(monkeypatch, search_answer: str, extractions: dict[str, PageExtraction]):
    monkeypatch.setattr(llm, "search_text", lambda prompt, model=None: (search_answer, ["q"]))
    monkeypatch.setattr(ingestion, "fetch_public_page",
                        lambda url: FetchResult(url, 200, "text/plain", PAGES[url]))

    def fake_structured(system, user, schema, model=None):
        url = user.split("\n", 1)[0].removeprefix("Source URL: ")
        return llm.LLMResult(extractions[url], model, 10, 10)
    monkeypatch.setattr(llm, "generate_structured", fake_structured)

    with SessionLocal() as db:
        uni = University(name="University of Southern California", normalized_name="university of southern california",
                         country="US", openalex_id="I1")
        db.add(uni)
        db.flush()
        prof = Professor(name="Quntao Zhuang", openalex_id="A1", university_id=uni.id)
        db.add(prof)
        db.commit()
        return prof.id


def test_candidate_urls_drop_social_and_aggregators():
    text = """https://www.linkedin.com/in/someone
https://scholar.google.com/citations?user=x
https://sites.usc.edu/zhuang/.
https://sites.usc.edu/zhuang/"""
    assert page_finder.candidate_urls(text) == ["https://sites.usc.edu/zhuang"]


def test_attaches_verified_page_to_existing_professor(monkeypatch):
    prof_id = setup(monkeypatch, "https://sites.usc.edu/zhuang/", {
        "https://sites.usc.edu/zhuang": page_extraction("Quntao Zhuang", "University of Southern California"),
    })
    with SessionLocal() as db:
        outcome = page_finder.find_faculty_page(db, prof_id)
        prof = db.get(Professor, prof_id)
        assert outcome.status == "found"
        assert prof.faculty_url == "https://sites.usc.edu/zhuang"
        assert prof.title == "Assistant Professor"
        assert db.query(Professor).count() == 1  # updated, not duplicated


def test_rejects_page_about_someone_else(monkeypatch):
    prof_id = setup(monkeypatch, "https://other.edu/qz", {
        "https://other.edu/qz": page_extraction("Q. Zhuang", "University of Elsewhere"),
    })
    with SessionLocal() as db:
        outcome = page_finder.find_faculty_page(db, prof_id)
        assert outcome.status == "not_found"
        assert "not" in outcome.attempts[0]["result"]
        assert db.get(Professor, prof_id).faculty_url is None


def test_rejects_same_name_at_different_university(monkeypatch):
    prof_id = setup(monkeypatch, "https://other.edu/qz", {
        "https://other.edu/qz": page_extraction("Quntao Zhuang", "University of Elsewhere"),
    })
    PAGES["https://other.edu/qz"] = "Quntao Zhuang\nUniversity of Elsewhere"
    with SessionLocal() as db:
        outcome = page_finder.find_faculty_page(db, prof_id)
        assert outcome.status == "not_found"
        assert "OpenAlex says" in outcome.attempts[0]["result"]


def test_university_acronym_matches_alias():
    from app.services.extraction import _same_university
    mit = University(name="Massachusetts Institute of Technology", aliases=["MIT"])
    assert _same_university("MIT", mit)
    assert not _same_university("Harvard University", mit)


def test_candidate_urls_accept_bare_www():
    assert page_finder.candidate_urls("Found: www.cs.umass.edu/~towsley/.") == ["https://www.cs.umass.edu/~towsley"]
