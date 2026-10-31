import asyncio

from mcp import Client

from app.mcp_server import server


async def _call(name: str, args: dict):
    async with Client(server) as client:
        return await client.call_tool(name, args)


def call(name: str, args: dict):
    """Call a tool through a real in-process MCP client session."""
    return asyncio.run(_call(name, args))


async def _list_tools():
    async with Client(server) as client:
        return (await client.list_tools()).tools


def test_lists_expected_tools_with_annotations():
    tools = {t.name: t for t in asyncio.run(_list_tools())}
    assert {"search_web", "ingest_and_extract", "search_openalex_topics", "get_professor",
            "start_discovery", "get_discovery_job"} <= set(tools)
    assert tools["get_professor"].annotations.read_only_hint is True
    assert tools["start_discovery"].annotations.read_only_hint is False
    assert not any("sql" in name for name in tools)


def test_ingest_text_and_read_back_lead(client, monkeypatch):
    from app.schemas.extraction import Claim, PageExtraction
    from app.services import llm
    empty = Claim(value=None, evidence_quote=None)
    ex = PageExtraction(page_kind="social_post", university=empty, department=empty, professor_name=empty,
                        professor_title=empty, institutional_email=empty, accepting_students=empty,
                        research_topics=[], degree_types=[], eligibility_requirements=[],
                        funding_details=[Claim(value="funded", evidence_quote="fully funded")],
                        application_deadline=empty, application_url=empty, warnings=[])
    monkeypatch.setattr(llm, "generate_structured", lambda *a: llm.LLMResult(ex, "m", 1, 1))

    result = call("ingest_and_extract", {"text": "Prof X has fully funded PhD spots"})
    assert not result.is_error
    assert result.structured_content["professor_id"] is None
    assert result.structured_content["verified_fields"] == 1


def test_start_and_poll_discovery_job(client):
    started = call("start_discovery", {"research_areas": ["quantum_computing"], "max_results": 5})
    job_id = started.structured_content["job_id"]
    polled = call("get_discovery_job", {"job_id": job_id})
    assert polled.structured_content["job"]["status"] == "queued"


def test_errors_are_tool_errors_not_crashes(client):
    assert call("get_professor", {"professor_id": "not-a-uuid"}).is_error
    assert call("get_candidate_profile", {}).is_error
    assert call("ingest_and_extract", {"url": "http://127.0.0.1/admin"}).is_error


def test_write_tools_need_confirmation_and_never_delete():
    tools = {t.name: t for t in asyncio.run(_list_tools())}
    for name in ("update_candidate_profile", "update_application"):
        assert tools[name].annotations.destructive_hint is True  # clients ask before changing the user's records
    assert not any(word in name for name in tools for word in ("delete", "remove", "sql"))


def test_profile_update_changes_only_given_fields(client):
    client.put("/api/v1/profile", json={"name": "Me", "skills": ["Python"], "research_interests": ["RAG"]})
    r = call("update_candidate_profile", {"skills": ["Python", "PyTorch"],
                                          "test_scores": [{"test": "IELTS", "score": "7.5"}]})
    assert not r.is_error
    assert r.structured_content["changed"]["skills"] == {"before": 1, "after": 2}
    saved = client.get("/api/v1/profile").json()
    assert saved["skills"] == ["Python", "PyTorch"] and saved["test_scores"][0]["score"] == "7.5"
    assert saved["research_interests"] == ["RAG"] and saved["name"] == "Me"  # untouched
    assert call("update_candidate_profile", {}).is_error


def test_track_then_update_application_appends_notes(client):
    from tests.test_tracker import seed_opportunity
    opp_id = seed_opportunity()
    app = call("track_opportunity", {"opportunity_id": opp_id, "note": "Strong fit"}).structured_content
    assert call("track_opportunity", {"opportunity_id": opp_id}).structured_content["id"] == app["id"]

    moved = call("update_application", {"application_id": app["id"], "status": "contacted",
                                        "add_note": "Emailed about Fall 2027"}).structured_content
    assert moved["status"] == "contacted" and moved["contacted_at"] is not None
    assert moved["notes"].startswith("Strong fit") and moved["notes"].endswith("Emailed about Fall 2027")
    listed = call("list_applications", {}).structured_content["result"]
    assert [a["id"] for a in listed] == [app["id"]]
    assert call("update_application", {"application_id": app["id"]}).is_error
    assert call("update_application", {"application_id": app["id"], "status": "bogus"}).is_error


def test_follow_up_draft_without_first_email_is_a_tool_error(client):
    from tests.test_tracker import seed_opportunity
    assert call("generate_draft", {"opportunity_id": seed_opportunity(), "kind": "follow_up"}).is_error
