"""Export stored pages as eval fixtures (Planning §17.1). Run from backend/: python -m evals.build_fixtures

Faculty fixtures expect the professor and university the pipeline accepted (identity checked against
OpenAlex). Program fixtures expect the quote-verified values currently on file, so they are a
regression baseline ("reviewed": false) until a person confirms them. Hand-written negatives in
fixtures/negatives.json are true ground truth and are never overwritten.
"""

import json
import re
from pathlib import Path

from sqlalchemy import select

from app.db.models import Evidence, Professor, Source, University
from app.db.session import SessionLocal

OUT = Path(__file__).parent / "fixtures"
PROGRAM_FIELDS = ["guaranteed_funding", "tuition_coverage", "stipend_amount", "application_deadline",
                  "pte_accepted", "international_applicants_accepted", "requires_masters_for_phd"]


def _slug(url: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", url.casefold().split("://", 1)[-1])[:80].strip("-")


def _text(source: Source) -> str:
    return source.extracted_text or source.raw_content or ""


def main() -> None:
    faculty, program = [], []
    with SessionLocal() as db:
        for prof, uni in db.execute(select(Professor, University).join(University)
                                    .where(Professor.faculty_url.is_not(None))):
            source = db.scalars(select(Source).where(Source.canonical_url == prof.faculty_url)
                                .order_by(Source.fetched_at.desc())).first()
            if source and _text(source):
                faculty.append({"id": _slug(source.canonical_url), "kind": "faculty", "url": source.canonical_url,
                                "text": _text(source), "reviewed": True,
                                "expected": {"professor_name": prof.name, "university": uni.name},
                                "university_aliases": uni.aliases or []})

        rows = db.scalars(select(Evidence).where(Evidence.entity_type == "program",
                                                 Evidence.verification_status == "quote_verified",
                                                 Evidence.field_name.in_(PROGRAM_FIELDS))).all()
        by_source: dict = {}
        for e in rows:
            by_source.setdefault(e.source_id, {})[e.field_name] = (e.claim_value_json or {}).get("value")
        for source_id, expected in by_source.items():
            source = db.get(Source, source_id)
            if source and _text(source):
                program.append({"id": _slug(source.canonical_url), "kind": "program", "url": source.canonical_url,
                                "text": _text(source), "reviewed": False, "expected": expected})

    for name, items in (("faculty.json", faculty), ("program.json", program)):
        (OUT / name).write_text(json.dumps(sorted(items, key=lambda f: f["id"]), indent=1, ensure_ascii=False))
        print(f"{name}: {len(items)} fixtures")


if __name__ == "__main__":
    main()
