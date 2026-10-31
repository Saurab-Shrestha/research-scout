"""Score author identity resolution on frozen OpenAlex candidates (Planning §17.2). Offline, no LLM.

    python -m evals.identity

Precision = picks that are the right person. Coverage = cases resolved when an answer exists.
A wrong pick attaches someone else's papers, so precision matters more than coverage: declining
("needs review") is safe, picking a namesake is not.
"""

import json
from pathlib import Path

from app.services.openalex import AuthorCandidate
from app.services.publications import choose_author

FIXTURES = Path(__file__).parent / "fixtures"


def load() -> list[dict]:
    return [c for name in ("identity.json", "identity_cases.json") for c in json.loads((FIXTURES / name).read_text())]


def run(cases: list[dict]) -> dict:
    results = []
    for case in cases:
        candidates = [AuthorCandidate(**c, api_url="", raw={}) for c in case["candidates"]]
        chosen, confidence, reason = choose_author(candidates, case["name"], case["institution_id"])
        got = chosen.openalex_id if chosen else None
        results.append({"id": case["id"], "expected": case["expected"], "got": got, "reason": reason,
                        "outcome": "correct" if got == case["expected"] else "abstained" if got is None else "wrong"})
    picks = [r for r in results if r["got"]]
    answerable = [r for r in results if r["expected"]]
    return {
        "cases": len(results),
        "accuracy": round(sum(r["outcome"] == "correct" for r in results) / len(results), 3),
        "precision": round(sum(r["outcome"] == "correct" for r in picks) / len(picks), 3) if picks else None,
        "coverage": round(sum(r["got"] == r["expected"] for r in answerable) / len(answerable), 3) if answerable else None,
        "wrong": [r for r in results if r["outcome"] == "wrong"],
        "abstained": [r for r in results if r["outcome"] == "abstained"],
    }


if __name__ == "__main__":
    summary = run(load())
    for r in summary["wrong"] + summary["abstained"]:
        print(f"{'✗' if r['outcome'] == 'wrong' else '?'} {r['id']}: expected {r['expected']}, got {r['got']} ({r['reason']})")
    print(json.dumps({k: v for k, v in summary.items() if k not in ("wrong", "abstained")}, indent=1))
