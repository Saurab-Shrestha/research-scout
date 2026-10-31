# Research Scout

A self-hosted assistant for finding graduate research positions: it finds professors who are actively
publishing in your research areas, checks their programs' official pages for funding, deadlines and
entry requirements, ranks the results against your profile, and helps you track applications and draft
outreach emails.

It covers bachelor's, master's (course-based and research) and PhD programs in 21 countries across North
America, Europe and Asia-Pacific.

> **Estimates, not advice.** Funding and eligibility are read from official pages where the app can find
> them, and otherwise fall back to typical defaults for the country. Every claim links to the page and the
> quote it came from. Check the official page before you rely on a date or a funding promise.
> Research Scout never sends email or submits anything on your behalf.

## What it does

- **Find researchers.** Searches [OpenAlex](https://openalex.org) for people actively publishing on your
  topics at universities in the countries you pick, then finds and verifies each one's faculty page.
  You can also add a single professor from their page or a pasted post.
- **Check programs.** Uses web search to find each program's official admissions and funding pages and
  extracts funding, stipend, deadlines, English test minimums and GPA requirements. Each fact must quote
  the page word for word or it's discarded.
- **Rank.** Scores every professor × degree on research fit (your interests compared with their recent
  papers), funding, eligibility, availability and timing, and shows the breakdown.
- **Apply.** A shortlist with side-by-side comparison, a kanban tracker with next steps, first-contact
  and follow-up email drafts grounded in your profile and the professor's papers, and calendar export of
  deadlines.
- **Use it from an AI assistant.** An optional [MCP](https://modelcontextprotocol.io) server exposes
  search, the tracker, drafts and profile edits to clients such as Claude Code.

## Quick start (Docker)

You need Docker and an API key for one AI provider: Google Gemini, OpenAI or Anthropic, or a local model
server such as Ollama.

```bash
git clone https://github.com/Saurab-Shrestha/research-scout.git
cd research-scout
cp .env.example .env        # set POSTGRES_PASSWORD; everything else is optional
docker compose up --build -d
```

Open http://localhost:8000. The Overview page walks you through four steps:

1. **Settings → AI provider:** pick a provider, paste your key, and press *Test connection*.
2. **Academic Profile:** your education, test scores, research interests and study plan (degrees,
   countries, intended start).
3. **Researchers → Add researchers:** start a discovery search.
4. **Researchers → Evaluate programs:** check funding and deadlines and rank everything.

A free [OpenAlex API key](https://openalex.org/settings/api) (`OPENALEX_API_KEY` in `.env`) raises
OpenAlex's rate limits; it works without one.

### AI providers

| Provider | Reading pages and drafting | Web search (finding pages) | Embeddings (research fit) |
|---|---|---|---|
| Google Gemini (AI Studio or Vertex AI) | yes | yes | yes |
| OpenAI | yes | yes | yes |
| Anthropic Claude | yes | yes | no; pick Gemini, OpenAI or a local model for embeddings |
| OpenAI-compatible (Ollama, LM Studio, vLLM, OpenRouter) | yes | no | yes |

Without web search, discovery can still find researchers through OpenAlex, but finding faculty pages and
checking programs won't work. Research-fit scores are calibrated for `gemini-embedding-001`. With another
embedding model they still rank researchers, but the 0–100 scale is a rough guess until it's calibrated
(see `SIM_RANGE` in `backend/app/services/matching.py`).

Settings saved in the app override `.env`. To run a local model from Docker, use
`http://host.docker.internal:11434/v1` as the server URL.

**What it costs:** a discovery run of 20 researchers plus a full evaluation is a few hundred model calls
and roughly 100 web searches. Enter your provider's prices under *Settings → AI provider → Prices* to see
the cost of each job.

## Security

Research Scout is a single-user app with **no login**. Docker binds it to `127.0.0.1`, so only your
machine can reach it. Don't expose it to a network or the internet: anyone who can reach it can read
your profile and use your AI keys. API keys saved in the app are stored in the local database and are
never sent back to the browser. See [SECURITY.md](SECURITY.md).

Page fetching blocks private and internal addresses, respects `robots.txt`, and treats page content as
untrusted data in its extraction prompts.

## Development

Requires Python 3.12 with [uv](https://docs.astral.sh/uv/), Node 24 and PostgreSQL.

```bash
uv sync
cp .env.example .env
createdb research_scout
createdb research_scout_test    # used by the test suite
uv run alembic upgrade head

uv run uvicorn app.main:app --app-dir backend --reload   # API on :8000, docs at /docs
(cd backend && uv run python -m app.worker)               # background jobs
(cd web && npm install && npm run dev)                    # web app on :5173, proxies /api to :8000
```

For a single server, build the web app once with `cd web && npm run build`; the API then serves it at
http://localhost:8000.

### Tests

```bash
uv run pytest                          # backend, includes the offline identity eval
uvx ruff check backend/app backend/tests
(cd web && npm run lint && npm run build && node e2e/ics.check.ts)
(cd web && npm run e2e)                # browser smoke test against a running app (WEB_URL, default :5173)
cd backend && uv run python -m evals.run   # extraction eval against a real model (costs API calls)
```

### Layout

```
backend/app/
  api/v1/        REST endpoints
  services/      discovery, extraction, programs, eligibility, matching, drafts, llm (provider adapter)
  workflows/     LangGraph jobs: discovery and evaluation, resumable from checkpoints
  core/          config, countries and their funding norms, URL safety
  mcp_server.py  MCP tools
backend/migrations/  Alembic
backend/evals/       extraction and identity evals with recorded fixtures
web/src/             React + TypeScript + Tailwind + shadcn/ui
docs/design.md       the original design document
```

### Backups

```bash
scripts/backup.sh             # local Postgres -> backups/<timestamp>.dump (keeps newest 14)
scripts/backup.sh --compose   # the compose db service
pg_restore --clean --if-exists -d research_scout backups/<file>.dump
```

### MCP server

`.mcp.json` registers `backend/app/mcp_server.py` for MCP clients started in this folder. It uses the
same database as the app (`DATABASE_URL` in `.env`; with Docker, the database is published on
`localhost:5433`). Profile and tracker edits are marked so clients ask before running them; there is no
generic SQL, arbitrary-write or delete tool.

## Contributing

Issues and pull requests are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md). A good first contribution
is adding a country: one line in `backend/app/core/countries.py` and one in `web/src/lib/format.ts`.

## License

[MIT](LICENSE)
