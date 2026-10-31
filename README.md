# Research Scout

Personal tool for finding funded AI/ML and quantum computing research positions in the USA and Canada. See `Planning.md` for the full design.

## Setup

Requires Python 3.12 (managed by `uv`), Node 24 and a local PostgreSQL.

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
(cd web && npm install && npm run dev)                    # web app on :5173 (proxies /api to :8000)
```

For a single server, build the web app once (`cd web && npm run build`); the API then serves it at
http://localhost:8000.

### Or with Docker

```bash
# .env needs POSTGRES_PASSWORD and the API keys
docker compose up --build -d     # db, migrations, worker, API + web app on :8000 (localhost only)
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
uv run pytest                    # backend, includes the offline identity eval
(cd web && npm run e2e)          # browser smoke test; needs the API and `npm run dev` running
cd backend && uv run python -m evals.identity   # identity-resolution report
```

## Status

Web app (`web/`, React + TypeScript + Tailwind + shadcn/ui), replacing the Streamlit UI:

- [x] Dashboard: summary, next actions, deadline timeline, top matches, and what's blocking you
- [x] Opportunities: filters kept in the URL, sortable table, side panel with score breakdown, quoted evidence and eligibility checks
- [x] Tracker: kanban with pointer and keyboard drag, card menu, editor with history
- [x] Draft studio: versions, edit, copy, open in mail app, mark as sent, professor's papers alongside
- [x] Discover: start discovery and evaluation jobs with live progress; add leads by URL or pasted post
- [x] Profile editor; light and dark themes; mobile layout

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
- [x] MCP server (`backend/app/mcp_server.py`, registered in `.mcp.json`): 19 tools across discovery, scholarly, workspace and applying groups (profile edits, tracker, drafts, evaluation); profile and tracker edits are marked for client confirmation; no generic SQL, arbitrary-write or delete tool
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
- [x] UI: add faculty URL or social post, professor details, candidate profile (now in the web app)
