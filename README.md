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
uv run streamlit run frontend/app.py                      # UI on :8501
```

## Test

```bash
uv run pytest
```

## Status

Milestone 1 in progress:

- [x] Project scaffold, config, Alembic migrations
- [x] Health endpoint and candidate profile (`GET`/`PUT /api/v1/profile`)
- [x] SSRF-safe, robots.txt-aware fetcher with redirect revalidation
- [x] Source ingestion (`POST /api/v1/sources/ingest`) for URLs and pasted posts, deduplicated
- [x] Gemini structured extraction with field-level evidence (`POST /api/v1/sources/{id}/extract`); quotes checked against page text
- [x] Professor records (`GET /api/v1/professors`, `GET /api/v1/professors/{id}` with evidence)
- [ ] Real-model eval on fixture pages (Vertex AI express: `GOOGLE_GENAI_USE_VERTEXAI=true` + `GOOGLE_API_KEY`)
- [x] OpenAlex identity resolution and recent publications (`POST /api/v1/professors/{id}/refresh`)
- [x] Streamlit UI: add faculty URL or social post, professor detail (research, publications, evidence), candidate profile
