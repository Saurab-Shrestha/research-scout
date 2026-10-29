"""Deterministic eligibility checks (Planning §12.1). Missing information is never treated as a pass."""

import re
from dataclasses import asdict, dataclass
from datetime import date

ORDER = {"fail": 0, "unknown": 1, "warn": 2, "ok": 3}


@dataclass
class Check:
    name: str
    status: str  # ok | warn | unknown | fail
    detail: str


def _score(text: str | None) -> float | None:
    match = re.search(r"\d+(?:\.\d+)?", text or "")
    return float(match.group()) if match else None


def check_english(profile: dict, requirements: dict) -> Check:
    tests = {t["test"].upper(): _score(t["score"]) for t in profile.get("test_scores", [])}
    pte = next((v for k, v in tests.items() if "PTE" in k), None)
    if not tests:
        return Check("english", "unknown", "No English test on profile.")
    if requirements.get("pte_accepted") == "no" and pte is not None and len(tests) == 1:
        return Check("english", "fail", "Program does not accept PTE; IELTS or TOEFL needed.")
    for req in requirements.get("english") or []:
        name, minimum = req["test"].upper(), _score(req.get("minimum"))
        mine = next((v for k, v in tests.items() if k.split()[0] in name or name.split()[0] in k), None)
        if mine is not None and minimum is not None:
            ok = mine >= minimum
            return Check("english", "ok" if ok else "fail",
                         f"{req['test']}: yours {mine:g}, minimum {minimum:g}.")
    if requirements.get("pte_accepted") == "yes" and pte is not None:
        return Check("english", "warn", f"PTE accepted; minimum not stated (yours {pte:g}).")
    return Check("english", "unknown", "Accepted tests or minimums not verified for your test.")


def check_gpa(profile: dict, requirements: dict) -> Check:
    stated = requirements.get("minimum_gpa")
    bachelors = next((e for e in profile.get("education", []) if e.get("gpa_scale")), None)
    if not stated:
        return Check("gpa", "unknown", "Minimum GPA not verified on program pages.")
    minimum = _score(stated)
    if not bachelors or bachelors.get("gpa_scale") != 4.0 or minimum is None:
        return Check("gpa", "unknown", f"Program states {stated!r}; your grade needs a 4.0-scale evaluation (e.g. WES).")
    ok = bachelors["gpa"] >= minimum
    return Check("gpa", "ok" if ok else "fail", f"Minimum {stated}; yours {bachelors['gpa']}/4.0.")


def check_degree(profile: dict, requirements: dict, country: str | None, degree_type: str) -> Check:
    has_masters = any("master" in (e.get("degree") or "").lower() or (e.get("degree") or "").upper().startswith("M")
                      for e in profile.get("education", []))
    if degree_type != "phd" or has_masters:
        return Check("degree", "ok", "Bachelor's satisfies the entry degree.")
    if requirements.get("requires_masters_for_phd") == "yes":
        return Check("degree", "fail", "Program requires a master's before the PhD.")
    if requirements.get("requires_masters_for_phd") == "no":
        return Check("degree", "ok", "Direct entry from a bachelor's is stated.")
    if country == "CA":
        return Check("degree", "warn", "Canadian PhDs usually require a master's; consider the thesis MSc route.")
    return Check("degree", "ok", "US PhDs usually admit from a bachelor's.")


def is_international(profile: dict) -> bool:
    # ponytail: inferred from education countries; add an explicit citizenship field if this misfires.
    return not any((e.get("country") or "").upper() in ("US", "CA") for e in profile.get("education", []))


def check_international(profile: dict, requirements: dict) -> Check:
    accepted = requirements.get("international_applicants_accepted")
    if not is_international(profile):
        return Check("international", "ok", "Domestic applicant.")
    if accepted == "no":
        return Check("international", "fail", "Program does not admit international applicants.")
    if accepted == "yes":
        return Check("international", "ok", "International applicants are admitted.")
    return Check("international", "ok", "No restriction on international applicants stated.")


def check_deadline(deadline: date | None, today: date) -> Check:
    if deadline is None:
        return Check("deadline", "unknown", "Deadline not verified.")
    if deadline < today:
        return Check("deadline", "fail", f"Deadline {deadline.isoformat()} has passed for this cycle.")
    return Check("deadline", "ok", f"Deadline {deadline.isoformat()} ({(deadline - today).days} days left).")


def evaluate(profile: dict, requirements: dict, country: str | None, degree_type: str,
             deadline: date | None, today: date) -> tuple[str, list[dict]]:
    checks = [check_degree(profile, requirements, country, degree_type), check_international(profile, requirements),
              check_english(profile, requirements),
              check_gpa(profile, requirements), check_deadline(deadline, today)]
    statuses = [c.status for c in checks]
    if "fail" in statuses:
        overall = "ineligible"
    elif statuses.count("unknown") >= 3:  # of degree, international, english, gpa, deadline
        overall = "insufficient_information"
    elif "unknown" in statuses or "warn" in statuses:
        overall = "potentially_eligible"
    else:
        overall = "eligible"
    return overall, [asdict(c) for c in checks]
