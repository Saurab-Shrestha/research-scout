"""Next-step suggestions for tracked applications (Planning §12.5)."""

from datetime import date, timedelta

STATUSES = ["shortlisted", "researching", "contacted", "replied", "applying", "submitted",
            "interview", "offer", "rejected", "declined", "withdrawn"]
CLOSED = {"offer", "rejected", "declined", "withdrawn"}


def suggest_next_action(country: str | None, degree_type: str, status: str, deadline: date | None,
                        today: date) -> tuple[str | None, date | None]:
    """Recommended next step and due date. Canada thesis routes need a supervisor before applying."""
    if status in CLOSED or status == "submitted":
        return None, None
    apply_by = deadline - timedelta(days=7) if deadline else None
    if status in ("shortlisted", "researching"):
        if country == "CA" and degree_type in ("thesis_masters", "phd"):
            return "Email the professor about supervision and funding before applying", today + timedelta(days=3)
        if degree_type == "phd":
            return "Optional: email the professor; start the application", min(filter(None, [apply_by, today + timedelta(days=14)]))
        return "Start the application; contact the professor about RA roles after admission", apply_by
    if status == "contacted":
        return "Follow up if no reply", today + timedelta(days=10)
    if status in ("replied", "applying", "interview"):
        return "Submit the application", apply_by
    return None, None
