import socket

import httpx
import pytest

from app.core.security import UnsafeURLError
from app.services import fetcher
from app.services.fetcher import FetchError, fetch_public_page

PUBLIC = {"uni.example.edu": "93.184.216.34", "evil.example.com": "10.0.0.5"}


def resolve(host, port, type=None):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (PUBLIC[host], port))]


def make_client(routes: dict[str, httpx.Response]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        return routes.get(str(request.url), httpx.Response(404))
    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.fixture(autouse=True)
def clear_robots_cache():
    fetcher._robots_cache.clear()


def html(body: str) -> httpx.Response:
    return httpx.Response(200, html=body)


def test_fetches_public_page():
    client = make_client({"https://uni.example.edu/jane": html("<h1>Prof Jane</h1>")})
    result = fetch_public_page("https://uni.example.edu/jane", client, resolve)
    assert result.status == 200
    assert result.content_type == "text/html"
    assert "Prof Jane" in result.content


def test_follows_safe_redirect():
    client = make_client({
        "https://uni.example.edu/old": httpx.Response(301, headers={"location": "/new"}),
        "https://uni.example.edu/new": html("moved"),
    })
    assert fetch_public_page("https://uni.example.edu/old", client, resolve).final_url == "https://uni.example.edu/new"


def test_revalidates_redirect_target():
    client = make_client({
        "https://uni.example.edu/x": httpx.Response(302, headers={"location": "http://evil.example.com/admin"}),
    })
    with pytest.raises(UnsafeURLError):
        fetch_public_page("https://uni.example.edu/x", client, resolve)


def test_respects_robots_txt():
    client = make_client({
        "https://uni.example.edu/robots.txt": httpx.Response(200, text="User-agent: *\nDisallow: /private"),
        "https://uni.example.edu/private/page": html("secret"),
    })
    with pytest.raises(FetchError, match="robots"):
        fetch_public_page("https://uni.example.edu/private/page", client, resolve)


def test_rejects_oversized_response(monkeypatch):
    monkeypatch.setattr(fetcher.settings, "fetch_max_bytes", 100)
    client = make_client({"https://uni.example.edu/big": html("x" * 1000)})
    with pytest.raises(FetchError, match="exceeds"):
        fetch_public_page("https://uni.example.edu/big", client, resolve)


def test_rejects_unsupported_content_type():
    client = make_client({
        "https://uni.example.edu/a.zip": httpx.Response(200, content=b"PK", headers={"content-type": "application/zip"}),
    })
    with pytest.raises(FetchError, match="content type"):
        fetch_public_page("https://uni.example.edu/a.zip", client, resolve)
