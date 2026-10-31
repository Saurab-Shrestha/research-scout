"""Deterministic eligibility checks (Planning §12.1). Missing information is never treated as a pass."""

import re
from dataclasses import asdict, dataclass
from datetime import date

from app.core import countries

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


# PhD applicants without a master's, by funding system. Unlisted systems: entry from a bachelor's is normal.
PHD_ENTRY = {
    "ca": "Canadian PhDs usually require a master's; consider the thesis MSc route.",
    "studentship": "UK and Irish PhDs often expect a master's or a first-class bachelor's.",
    "position": "European PhDs usually require a master's; consider a master's there first.",
    "contract": "European PhDs usually require a master's; consider a master's there first.",
    "anz": "Australian and NZ PhDs expect honours or a research master's; check whether your bachelor's counts.",
    "jp": "Japanese doctoral courses require a master's; apply to the master's course first.",
    "kr": "Korean PhDs usually require a master's; consider the integrated MS-PhD track.",
}


def check_degree(profile: dict, requirements: dict, country: str | None, degree_type: str) -> Check:
    has_masters = any("master" in (e.get("degree") or "").lower() or (e.get("degree") or "").upper().startswith("M")
                      for e in profile.get("education", []))
    if degree_type == "bachelors":
        if profile.get("education"):
            return Check("degree", "ok", "Secondary-school completion is the entry requirement.")
        return Check("degree", "unknown", "Add your secondary-school record to the profile.")
    if degree_type != "phd" or has_masters:
        return Check("degree", "ok", "Bachelor's satisfies the entry degree.")
    if requirements.get("requires_masters_for_phd") == "yes":
        return Check("degree", "fail", "Program requires a master's before the PhD.")
    if requirements.get("requires_masters_for_phd") == "no":
        return Check("degree", "ok", "Direct entry from a bachelor's is stated.")
    if note := PHD_ENTRY.get(countries.system(country)):
        return Check("degree", "warn", note)
    return Check("degree", "ok", "US PhDs usually admit from a bachelor's.")


def is_international(profile: dict, country: str | None) -> bool:
    # ponytail: inferred from where you studied; add an explicit citizenship field if this misfires.
    return not any((e.get("country") or "").upper() == country for e in profile.get("education", []))


def check_international(profile: dict, requirements: dict, country: str | None) -> Check:
    accepted = requirements.get("international_applicants_accepted")
    if not is_international(profile, country):
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
    checks = [check_degree(profile, requirements, country, degree_type), check_international(profile, requirements, country),
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
