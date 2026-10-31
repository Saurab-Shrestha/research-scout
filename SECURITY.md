# Security

## How Research Scout is meant to run

Research Scout is a single-user app you run on your own machine. It has **no login and no user
accounts**. The Docker setup publishes the app (port 8000) and the database (port 5433) on `127.0.0.1`
only.

Do not put it on a server, a shared network or the internet without adding authentication in front of
it, for example a reverse proxy with login. Anyone who can reach the app can:

- read and change your academic profile, tracker and drafts;
- start jobs that spend your AI provider credits;
- replace the AI provider settings, including keys (saved keys are never returned by the API, but they
  can be overwritten).

## What the app does to stay safe

- **Fetching pages:** only `http`/`https` on ports 80 and 443; any host that resolves to a non-public
  address (private, loopback, link-local) is refused, checked again after every redirect; `robots.txt`
  is respected. See `backend/app/core/security.py`. Known limit: the address is checked before
  connecting, which leaves a DNS-rebinding window, one more reason to keep the app on localhost.
- **Prompt injection:** fetched pages are wrapped as untrusted content, and extracted facts are kept only
  when their quote appears word for word on the page. A prompt-injection fixture is part of the eval set.
- **Keys:** keys set in the app are stored in the local Postgres database; keys in `.env` stay there.
  Neither is logged or returned by the API.
- **Email:** the app drafts emails but never sends them.
- **MCP server:** profile and tracker edits are annotated so MCP clients ask for confirmation; there is
  no SQL, generic write or delete tool.

## Reporting a vulnerability

Please report security problems privately through
[GitHub security advisories](https://github.com/Saurab-Shrestha/ProfSearch/security/advisories/new)
rather than a public issue. Include steps to reproduce. You should get a reply within a week.
