"""Run extraction prompts on stored fixture pages and score them (Planning §17.2).

    python -m evals.run                 # all fixtures, real model (costs ~1 Gemini call per fixture)
    python -m evals.run --kind faculty --limit 5
"""

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

from app.core.config import settings
from app.db.models import University
from app.prompts import extraction as faculty_prompt, program_extraction as program_prompt
from app.schemas.extraction import Claim, PageExtraction
from app.schemas.program import ProgramExtraction
from app.services import llm
from app.services.extraction import _is_supported, _norm, _same_university
from app.services.publications import _name_key

HERE = Path(__file__).parent
PROMPTS = {"faculty": (faculty_prompt, PageExtraction), "program": (program_prompt, ProgramExtraction)}


def load(kind: str | None) -> list[dict]:
    fixtures = [f for name in ("faculty.json", "program.json", "negatives.json")
                for f in json.loads((HERE / "fixtures" / name).read_text())]
    return [f for f in fixtures if kind in (None, f["kind"])]


def matches(field: str, expected, got, fixture: dict) -> bool:
    if expected is None or got is None:
        return expected is got
    if field == "professor_name":
        return _name_key(expected) == _name_key(got)
    if field == "university":
        return _same_university(got, University(name=expected, aliases=fixture.get("university_aliases", [])))
    if field == "stipend_amount":
        try:
            return float(str(expected).replace(",", "")) == float(str(got).replace(",", ""))
        except ValueError:
            return False
    return _norm(str(expected)) == _norm(str(got))


def claims(parsed) -> list[Claim]:
    out = []
    for value in parsed.__dict__.values():
        out += [v for v in (value if isinstance(value, list) else [value]) if isinstance(v, Claim) and v.value]
    return out


def evaluate(fixture: dict) -> dict:
    prompt, schema = PROMPTS[fixture["kind"]]
    text = fixture["text"][: settings.extraction_max_chars]
    start = time.monotonic()
    try:
        result = llm.generate_structured(prompt.SYSTEM, prompt.build_user_message(fixture["url"], text),
                                         schema)
    except llm.LLMError as e:
        return {"id": fixture["id"], "error": str(e)}
    parsed, page = result.parsed, _norm(text)
    fields = {}
    for field, expected in fixture["expected"].items():
        got = getattr(parsed, field).value
        fields[field] = {"expected": expected, "got": got, "ok": matches(field, expected, got, fixture)}
    made = claims(parsed)
    return {"id": fixture["id"], "kind": fixture["kind"], "reviewed": fixture["reviewed"], "fields": fields,
            "claims": len(made), "supported": sum(_is_supported(c, page) for c in made),
            "seconds": round(time.monotonic() - start, 1),
            "tokens": result.input_tokens + result.output_tokens}


def summarize(results: list[dict]) -> dict:
    ok = [r for r in results if "error" not in r]
    summary = {"fixtures": len(results), "errors": len(results) - len(ok)}
    for label, subset in (("faculty", [r for r in ok if r["kind"] == "faculty"]),
                          ("program", [r for r in ok if r["kind"] == "program"]),
                          ("reviewed", [r for r in ok if r["reviewed"]])):
        checks = [f["ok"] for r in subset for f in r["fields"].values()]
        summary[f"{label}_field_accuracy"] = round(sum(checks) / len(checks), 3) if checks else None
    total = sum(r["claims"] for r in ok)
    summary["evidence_coverage"] = round(sum(r["supported"] for r in ok) / total, 3) if total else None
    summary["tokens"] = sum(r["tokens"] for r in ok)
    summary["mean_seconds"] = round(sum(r["seconds"] for r in ok) / len(ok), 1) if ok else None
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kind", choices=["faculty", "program"])
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    fixtures = load(args.kind)[: args.limit]
    with ThreadPoolExecutor(5) as pool:
        results = list(pool.map(evaluate, fixtures))
    summary = summarize(results) | {"model": llm.config().chat_model, "prompts":
                                    {"faculty": faculty_prompt.VERSION, "program": program_prompt.VERSION}}
    for r in results:
        bad = {k: v for k, v in r.get("fields", {}).items() if not v["ok"]}
        if "error" in r or bad:
            print(f"✗ {r['id']}: {r.get('error') or bad}")
    print(json.dumps(summary, indent=1))
    out = HERE / "results" / f"{datetime.now(UTC):%Y%m%dT%H%M%S}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"summary": summary, "results": results}, indent=1, ensure_ascii=False))
    print(f"saved {out}")


if __name__ == "__main__":
    main()
