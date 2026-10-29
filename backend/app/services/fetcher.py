"""Polite, SSRF-safe fetching of public web pages."""

import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from app.core.config import settings
from app.core.security import check_url_safe

# ponytail: text only; add PDF (PyMuPDF) when funding/admissions PDFs are needed.
ALLOWED_CONTENT_TYPES = {"text/html", "application/xhtml+xml", "text/plain"}

_robots_cache: dict[str, RobotFileParser] = {}


class FetchError(Exception):
    pass


@dataclass
class FetchResult:
    final_url: str
    status: int
    content_type: str
    content: str


def _robots_allows(client: httpx.Client, url: str) -> bool:
    parts = urlsplit(url)
    origin = f"{parts.scheme}://{parts.netloc}"
    parser = _robots_cache.get(origin)
    if parser is None:
        parser = RobotFileParser()
        r = client.get(f"{origin}/robots.txt")
        # RFC 9309: 4xx means no restrictions, 5xx means assume full disallow.
        # ponytail: redirects on robots.txt are treated as unavailable (allow); follow them if it matters.
        if r.status_code == 200:
            parser.parse(r.text.splitlines())
        elif r.status_code >= 500:
            parser.parse(["User-agent: *", "Disallow: /"])
        else:
            parser.parse([])
        _robots_cache[origin] = parser
    return parser.can_fetch(settings.user_agent, url)


def fetch_public_page(url: str, client: httpx.Client | None = None, resolve=socket.getaddrinfo) -> FetchResult:
    own_client = client is None
    client = client or httpx.Client(
        timeout=settings.fetch_timeout_s,
        headers={"User-Agent": settings.user_agent},
    )
    try:
        current = url
        for _ in range(settings.fetch_max_redirects + 1):
            check_url_safe(current, resolve)
            if not _robots_allows(client, current):
                raise FetchError(f"disallowed by robots.txt: {current}")
            with client.stream("GET", current, follow_redirects=False) as r:
                if r.is_redirect:
                    current = urljoin(current, r.headers["location"])
                    continue
                if r.status_code >= 400:
                    raise FetchError(f"HTTP {r.status_code} for {current}")
                content_type = r.headers.get("content-type", "").split(";")[0].strip().lower()
                if content_type not in ALLOWED_CONTENT_TYPES:
                    raise FetchError(f"unsupported content type: {content_type or 'unknown'}")
                body = bytearray()
                for chunk in r.iter_bytes():
                    body += chunk
                    if len(body) > settings.fetch_max_bytes:
                        raise FetchError(f"response exceeds {settings.fetch_max_bytes} bytes")
                text = bytes(body).decode(r.encoding or "utf-8", errors="replace")
                return FetchResult(current, r.status_code, content_type, text)
        raise FetchError("too many redirects")
    except httpx.HTTPError as e:
        raise FetchError(f"request failed: {e}") from e
    finally:
        if own_client:
            client.close()
