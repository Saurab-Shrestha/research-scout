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
