# Research Scout

Personal tool for finding funded AI/ML and quantum computing research positions in the USA and Canada. See `Planning.md` for the full design.

## Setup

Requires Python 3.12 (managed by `uv`) and a local PostgreSQL.

```bash
uv sync
cp .env.example .env            # set CONTACT_EMAIL
createdb research_scout
createdb research_scout_test    # used by the test suite
uv run alembic upgrade head
```

## Run

```bash
uv run uvicorn app.main:app --app-dir backend --reload   # API on :8000, docs at /docs
(cd backend && uv run python -m app.worker)               # job worker (discovery searches)
uv run streamlit run frontend/app.py                      # UI on :8501
```

## Test

```bash
uv run pytest
```

## Status

Milestone 2 (discovery workflow) in progress:

- [x] Postgres job queue (`SKIP LOCKED`) with retries and stale-lock recovery
- [x] LangGraph discovery graph with Postgres checkpointer; failed jobs resume from the last completed node
- [x] Scholarly-first discovery: OpenAlex topics → active US/CA authors → professors → recent publications
- [x] `POST/GET /api/v1/research-jobs`, `GET /api/v1/research-jobs/{id}/events`; Discover page in the UI
- [x] Faculty page discovery: Gemini + Google Search proposes URLs; each is fetched, extracted and accepted only if name and university match (`POST /api/v1/professors/{id}/find-page`)
- [x] MCP server (`backend/app/mcp_server.py`, registered in `.mcp.json`): 12 tools across discovery, scholarly and workspace groups; no generic SQL/write tool
- [x] Gemini topic planner: picks relevant OpenAlex topics from candidates, covers every selected area, falls back to best match per query

Milestone 1 (complete except fixture evals):

- [x] Project scaffold, config, Alembic migrations
- [x] Health endpoint and candidate profile (`GET`/`PUT /api/v1/profile`)
- [x] SSRF-safe, robots.txt-aware fetcher with redirect revalidation
- [x] Source ingestion (`POST /api/v1/sources/ingest`) for URLs and pasted posts, deduplicated
- [x] Gemini structured extraction with field-level evidence (`POST /api/v1/sources/{id}/extract`); quotes checked against page text
- [x] Professor records (`GET /api/v1/professors`, `GET /api/v1/professors/{id}` with evidence)
- [ ] Real-model eval on fixture pages (Vertex AI express: `GOOGLE_GENAI_USE_VERTEXAI=true` + `GOOGLE_API_KEY`)
- [x] OpenAlex identity resolution and recent publications (`POST /api/v1/professors/{id}/refresh`)
- [x] Streamlit UI: add faculty URL or social post, professor detail (research, publications, evidence), candidate profile
