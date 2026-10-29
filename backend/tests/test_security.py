import socket

import pytest

from app.core.security import UnsafeURLError, canonicalize_url, check_url_safe


def fake_resolver(ip):
    def resolve(host, port, type=None):
        family = socket.AF_INET6 if ":" in ip else socket.AF_INET
        return [(family, socket.SOCK_STREAM, 6, "", (ip, port))]
    return resolve


@pytest.mark.parametrize("raw, expected", [
    ("HTTPS://CS.Example.EDU:443/people/jane/?utm_source=x&b=2&a=1#bio",
     "https://cs.example.edu/people/jane?a=1&b=2"),
    ("http://example.edu", "http://example.edu/"),
    ("https://example.edu:8443/x", "https://example.edu:8443/x"),
    ("https://user:pw@example.edu/x?fbclid=abc", "https://example.edu/x"),
])
def test_canonicalize_url(raw, expected):
    assert canonicalize_url(raw) == expected


@pytest.mark.parametrize("url, ip", [
    ("http://localhost/", "127.0.0.1"),
    ("http://internal.example/", "10.1.2.3"),
    ("http://meta.example/", "169.254.169.254"),
    ("http://v6.example/", "::1"),
    ("http://mapped.example/", "::ffff:192.168.0.1"),
    ("http://cgnat.example/", "100.64.0.1"),
])
def test_blocks_non_public_addresses(url, ip):
    with pytest.raises(UnsafeURLError):
        check_url_safe(url, fake_resolver(ip))


@pytest.mark.parametrize("url", [
    "ftp://example.edu/file",
    "file:///etc/passwd",
    "https://user:pw@example.edu/",
    "https://example.edu:2375/",
    "https:///nohost",
])
def test_blocks_bad_url_shapes(url):
    with pytest.raises(UnsafeURLError):
        check_url_safe(url, fake_resolver("93.184.216.34"))


def test_allows_public_address():
    check_url_safe("https://example.edu/faculty", fake_resolver("93.184.216.34"))
