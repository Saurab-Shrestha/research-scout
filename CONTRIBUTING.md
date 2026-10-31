# Contributing

Thanks for helping. Bug reports, fixes, new countries and better defaults are all welcome.

## Before you start

- For anything bigger than a small fix, open an issue first so we can agree on the approach.
- Keep changes focused: one pull request per fix or feature.

## Setup

Follow **Development** in the [README](README.md). You need Python 3.12 with uv, Node 24 and PostgreSQL
(the tests use a database named `research_scout_test`).

## Checks

These run in CI on every pull request; run them locally first:

```bash
uv run pytest
uvx ruff check backend/app backend/tests
cd web && npm run lint && npm run build && node e2e/ics.check.ts
```

Tests must not call real AI providers or the network. Monkeypatch `llm.generate_structured`,
`llm.search_text`, `llm.embed` and the OpenAlex client, as the existing tests do.

## Ground rules for the data

The app is only useful if users can trust what it shows. Please keep these:

- **Never invent facts.** Funding, deadlines and requirements come from a quoted official page or are
  labelled as a default or unknown. Don't fill gaps with model guesses.
- **Keep the evidence.** New extracted fields need an evidence quote and a check that the quote is on the
  page.
- **No automatic sending.** The app drafts; the user sends.

## Common contributions

- **Add a country:** add it to `COUNTRIES` in `backend/app/core/countries.py` with the funding system it
  follows, and to `REGIONS` in `web/src/lib/format.ts`. If no existing system fits, add one to
  `DEFAULTS` in `backend/app/services/programs.py` and `PHD_ENTRY` in
  `backend/app/services/eligibility.py`, with a test.
- **Calibrate an embedding model:** measure cosine similarities for loosely related and strongly matched
  papers and add a row to `SIM_RANGE` in `backend/app/services/matching.py`.
- **Database changes:** add an Alembic migration in `backend/migrations/versions/`.

## Style

Match the code around you. Python is checked with ruff; TypeScript with `tsc` and oxlint. Write commit
messages in the imperative ("Add Japan funding defaults").
