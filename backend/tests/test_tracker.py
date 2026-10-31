from datetime import date, timedelta

from app.db.models import CandidateProfile, Opportunity, Professor, Program, University
from app.db.session import SessionLocal
from app.services.tracker import suggest_next_action

TODAY = date(2026, 10, 29)


def test_canada_thesis_route_contacts_supervisor_first():
    action, due = suggest_next_action("CA", "thesis_masters", "shortlisted", date(2026, 12, 1), TODAY)
    assert "before applying" in action and due == TODAY + timedelta(days=3)


def test_us_phd_due_before_deadline():
    action, due = suggest_next_action("US", "phd", "shortlisted", date(2026, 11, 10), TODAY)
    assert due == date(2026, 11, 3)


def test_closed_status_has_no_next_action():
    assert suggest_next_action("US", "phd", "rejected", None, TODAY) == (None, None)


def seed_opportunity() -> str:
    with SessionLocal() as db:
        db.add(CandidateProfile(name="Me"))
        uni = University(name="UofT", normalized_name="uoft", country="CA")
        db.add(uni)
        db.flush()
        prof = Professor(name="Roger Grosse", university_id=uni.id)
        prog = Program(university_id=uni.id, name="PhD CS", normalized_name="phd cs", degree_type="phd",
                       deadline=date(2026, 12, 1))
        db.add_all([prof, prog])
        db.flush()
        opp = Opportunity(professor_id=prof.id, program_id=prog.id, degree_type="phd", title="PhD with Roger Grosse")
        db.add(opp)
        db.commit()
        return str(opp.id)


def test_tracker_lifecycle(client):
    opp_id = seed_opportunity()
    first = client.post("/api/v1/applications", json={"opportunity_id": opp_id})
    again = client.post("/api/v1/applications", json={"opportunity_id": opp_id})
    assert first.status_code == 201 and again.json()["id"] == first.json()["id"]
    app = first.json()
    assert app["deadline"] == "2026-12-01" and "before applying" in app["next_action"]

    updated = client.patch(f"/api/v1/applications/{app['id']}", json={"status": "contacted", "notes": "Sent email"}).json()
    assert updated["contacted_at"] is not None
    assert updated["next_action"] == "Follow up if no reply"
    assert [h["status"] for h in updated["history"]] == ["shortlisted", "contacted"]

    assert client.patch(f"/api/v1/applications/{app['id']}", json={"status": "bogus"}).status_code == 422
    assert client.delete(f"/api/v1/applications/{app['id']}").status_code == 204
    assert client.get("/api/v1/applications").json() == []


def test_outside_the_us_contacts_supervisor_first():
    action, _ = suggest_next_action("DE", "phd", "shortlisted", None, TODAY)
    assert "before applying" in action
