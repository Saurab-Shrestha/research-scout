"""Freeze OpenAlex author searches for identity-resolution evals. Run from backend/: python -m evals.build_identity

For each professor, searches by name only (no institution filter), so namesakes at other universities
appear as distractors, and merges the institution-filtered results production uses. Expected IDs are the
identities on file ("reviewed": false baseline); hand-written hard cases live in identity_cases.json.
"""

import json
from dataclasses import asdict
from pathlib import Path

from sqlalchemy import select

from app.db.models import Professor, University
from app.db.session import SessionLocal
from app.services import openalex

OUT = Path(__file__).parent / "fixtures" / "identity.json"


def _slim(c: openalex.AuthorCandidate) -> dict:
    return {k: v for k, v in asdict(c).items() if k not in ("raw", "api_url")}


def main() -> None:
    cases = []
    with SessionLocal() as db:
        rows = db.execute(select(Professor, University).join(University)
                          .where(Professor.openalex_id.is_not(None), University.openalex_id.is_not(None))).all()
        for prof, uni in rows:
            by_id = {c.openalex_id: c for c in openalex.search_authors(prof.name)}
            by_id |= {c.openalex_id: c for c in openalex.search_authors(prof.name, uni.openalex_id)}
            cases.append({"id": prof.name, "name": prof.name, "institution_id": uni.openalex_id,
                          "university": uni.name, "expected": prof.openalex_id, "reviewed": False,
                          "candidates": [_slim(c) for c in by_id.values()]})
    OUT.write_text(json.dumps(sorted(cases, key=lambda c: c["id"]), indent=1, ensure_ascii=False))
    namesakes = sum(sum(1 for c in case["candidates"] if c["openalex_id"] != case["expected"]) for case in cases)
    print(f"{len(cases)} professors, {namesakes} distractor profiles")


if __name__ == "__main__":
    main()
