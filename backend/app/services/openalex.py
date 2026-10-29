"""OpenAlex client: institutions, author identity resolution and recent works."""

import re
from dataclasses import dataclass

import httpx

from app.core.config import settings

BASE = "https://api.openalex.org"
WORK_FIELDS = "id,doi,title,publication_year,primary_location,open_access,abstract_inverted_index,authorships"
ARXIV_RE = re.compile(r"arxiv\.org/(?:abs|pdf)/([0-9]{4}\.[0-9]{4,5})")


class ScholarlyError(Exception):
    pass


@dataclass
class AuthorCandidate:
    openalex_id: str
    name: str
    orcid: str | None
    works_count: int
    current_institution_ids: list[str]
    api_url: str
    raw: dict


@dataclass
class Work:
    openalex_id: str
    doi: str | None
    arxiv_id: str | None
    title: str
    abstract: str | None
    publication_year: int | None
    url: str | None
    open_access_url: str | None
    author_position: str | None


def _get(path: str, params: dict) -> dict:
    params = {k: v for k, v in params.items() if v is not None}
    if settings.openalex_api_key:
        params["api_key"] = settings.openalex_api_key
    elif settings.contact_email:
        params["mailto"] = settings.contact_email
    try:
        r = httpx.get(f"{BASE}{path}", params=params, timeout=20,
                      headers={"User-Agent": settings.user_agent})
    except httpx.HTTPError as e:
        raise ScholarlyError(f"OpenAlex request failed: {e}") from e
    if r.status_code == 429:
        raise ScholarlyError("OpenAlex budget exhausted; set OPENALEX_API_KEY or retry after reset")
    if r.status_code >= 400:
        raise ScholarlyError(f"OpenAlex HTTP {r.status_code}: {r.text[:200]}")
    return r.json()


def short_id(url_id: str) -> str:
    """'https://openalex.org/A123' -> 'A123'."""
    return url_id.rsplit("/", 1)[-1]


def _strip(prefix: str, value: str | None) -> str | None:
    return value.removeprefix(prefix).lower() if value else None


def find_institution(name: str, country: str | None = None) -> dict | None:
    results = _get("/institutions", {"search": name, "per_page": 5})["results"]
    if country:
        results = [r for r in results if r.get("country_code") == country] or results
    return results[0] if results else None


def search_authors(name: str, institution_id: str | None = None, orcid: str | None = None) -> list[AuthorCandidate]:
    if orcid:
        params = {"filter": f"orcid:{orcid}"}
    else:
        params = {"search": name, "per_page": 10}
        if institution_id:
            params["filter"] = f"affiliations.institution.id:{institution_id}"
    data = _get("/authors", params)
    return [
        AuthorCandidate(
            openalex_id=short_id(a["id"]),
            name=a["display_name"],
            orcid=_strip("https://orcid.org/", a.get("orcid")),
            works_count=a.get("works_count", 0),
            current_institution_ids=[short_id(i["id"]) for i in a.get("last_known_institutions") or []],
            api_url=f"{BASE}/authors/{short_id(a['id'])}",
            raw=a,
        )
        for a in data["results"]
    ]


def _abstract(inverted: dict | None) -> str | None:
    if not inverted:
        return None
    positions = sorted((i, word) for word, idxs in inverted.items() for i in idxs)
    return " ".join(word for _, word in positions)


def recent_works(author_id: str, from_year: int, limit: int = 20) -> list[Work]:
    data = _get("/works", {
        "filter": f"author.id:{author_id},from_publication_date:{from_year}-01-01",
        "sort": "publication_date:desc",
        "per_page": limit,
        "select": WORK_FIELDS,
    })
    works = []
    for w in data["results"]:
        location = w.get("primary_location") or {}
        oa_url = (w.get("open_access") or {}).get("oa_url")
        arxiv = ARXIV_RE.search(" ".join(filter(None, [location.get("landing_page_url"), oa_url, w.get("doi")])) or "")
        position = next((a["author_position"] for a in w.get("authorships", [])
                         if (a.get("author") or {}).get("id") and short_id(a["author"]["id"]) == author_id), None)
        works.append(Work(
            openalex_id=short_id(w["id"]),
            doi=_strip("https://doi.org/", w.get("doi")),
            arxiv_id=arxiv.group(1) if arxiv else None,
            title=w.get("title") or "(untitled)",
            abstract=_abstract(w.get("abstract_inverted_index")),
            publication_year=w.get("publication_year"),
            url=location.get("landing_page_url"),
            open_access_url=oa_url,
            author_position=position,
        ))
    return works


AUTHOR_FIELDS = "id,display_name,orcid,works_count,summary_stats,affiliations,last_known_institutions"


def search_topics(query: str, limit: int = 3) -> list[dict]:
    return [{"id": short_id(t["id"]), "name": t["display_name"]}
            for t in _get("/topics", {"search": query, "per_page": limit})["results"]]


def top_authors_for_topics(topic_ids: list[str], countries: list[str], from_year: int, limit: int = 200) -> list[dict]:
    """Authors with the most recent works in these topics at institutions in these countries."""
    data = _get("/works", {
        "filter": f"topics.id:{'|'.join(topic_ids)},institutions.country_code:{'|'.join(countries)},"
                  f"from_publication_date:{from_year}-01-01",
        "group_by": "authorships.author.id",
        "per_page": min(limit, 200),
    })
    return [{"id": short_id(g["key"]), "name": g["key_display_name"], "topic_works": g["count"]}
            for g in data["group_by"] if g["key"]]


def get_authors(author_ids: list[str]) -> list[dict]:
    authors = []
    for i in range(0, len(author_ids), 100):  # OpenAlex allows up to 100 OR-ed values
        batch = author_ids[i:i + 100]
        authors += _get("/authors", {
            "filter": f"ids.openalex:{'|'.join(batch)}", "per_page": 100, "select": AUTHOR_FIELDS,
        })["results"]
    return authors


def institution_aliases(institution_id: str) -> list[str]:
    inst = _get(f"/institutions/{institution_id}", {"select": "display_name_acronyms,display_name_alternatives"})
    return list(dict.fromkeys((inst.get("display_name_acronyms") or []) + (inst.get("display_name_alternatives") or [])))
