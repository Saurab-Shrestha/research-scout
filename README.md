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

### Or with Docker

```bash
# .env needs POSTGRES_PASSWORD and the API keys
docker compose up --build -d     # db, migrations, API :8000, worker, UI :8501 (localhost only)
```

## Backups

```bash
scripts/backup.sh             # local Postgres -> backups/<timestamp>.dump (keeps newest 14)
scripts/backup.sh --compose   # the compose db service
pg_restore --clean --if-exists -d research_scout backups/<file>.dump
```

## Cost tracking

Each job records `tokens_used` and `cost_usd` (`GET /api/v1/research-jobs/{id}`). Set
`LLM_USD_PER_MILLION_INPUT`, `LLM_USD_PER_MILLION_OUTPUT` and `GROUNDED_SEARCH_USD_EACH` in `.env`
from your Vertex AI pricing page; left blank, cost stays 0 and only tokens are tracked.

## Test

```bash
uv run pytest
```

## Status

Milestone 6 (hardening):

- [x] Docker image and compose stack (db, one-shot migrations, API, worker, UI), ports bound to localhost
- [x] Database backups with rotation
- [x] Per-job token and cost recording
- [x] Security: SSRF guard tests, prompt-injection eval fixture, no write/SQL tools over MCP

Milestone 5 (draft studio):

- [x] Professor email and SOP outline drafts per opportunity (`POST/GET /api/v1/opportunities/{id}/drafts`, `PATCH /api/v1/drafts/{id}`)
- [x] Grounded in profile, stored papers and verified program facts; citations checked against stored publications; never sent automatically
- [x] Drafts tab on the opportunity detail with warnings and editable text

Milestone 4 (tracker):

- [x] `applications` with status history, deadlines and suggested next steps (Canada thesis routes: contact supervisor first)
- [x] `POST/GET/PATCH/DELETE /api/v1/applications`; Tracker page with editable status, due dates and notes; "Save to tracker" on opportunities

Milestone 3 (funding, eligibility, ranking):

- [x] Program verification: grounded search for official admissions/funding pages, quoted extraction, university/domain checks
- [x] Deterministic funding classification with US/CA defaults; international-admission, English, GPA, degree and deadline checks
- [x] Research fit from embeddings of interests vs recent papers; weighted score; exclusions (ineligible, unfunded for you)
- [x] `POST /api/v1/opportunities/evaluate` (background job), ranked `GET /api/v1/opportunities`, detail with evidence; Opportunities page

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
- [x] Real-model eval on fixture pages: `cd backend && uv run python -m evals.run` (rebuild fixtures from stored pages with `python -m evals.build_fixtures`)
- [x] OpenAlex identity resolution and recent publications (`POST /api/v1/professors/{id}/refresh`)
- [x] Streamlit UI: add faculty URL or social post, professor detail (research, publications, evidence), candidate profile
