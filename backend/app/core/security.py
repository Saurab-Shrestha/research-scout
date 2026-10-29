"""URL canonicalisation and SSRF protection for user-supplied and discovered URLs."""

import ipaddress
import socket
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

DEFAULT_PORTS = {"http": 80, "https": 443}
TRACKING_PARAMS = {"fbclid", "gclid", "mc_cid", "mc_eid", "ref", "trk"}


class UnsafeURLError(ValueError):
    pass


def canonicalize_url(url: str) -> str:
    """Normalise a URL so the same page always maps to the same key."""
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    if ":" in host:  # IPv6 literal
        host = f"[{host}]"
    netloc = host if parts.port in (None, DEFAULT_PORTS.get(scheme)) else f"{host}:{parts.port}"
    path = parts.path or "/"
    if len(path) > 1:
        path = path.rstrip("/")
    query = urlencode(sorted(
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.lower().startswith("utm_") and k.lower() not in TRACKING_PARAMS
    ))
    return urlunsplit((scheme, netloc, path, query, ""))


def check_url_safe(url: str, resolve=socket.getaddrinfo) -> None:
    """Raise UnsafeURLError unless every address the host resolves to is public.

    Must be called on the initial URL and again on every redirect target.
    """
    parts = urlsplit(url)
    if parts.scheme not in DEFAULT_PORTS:
        raise UnsafeURLError(f"scheme not allowed: {parts.scheme!r}")
    if not parts.hostname:
        raise UnsafeURLError("missing host")
    if parts.username or parts.password:
        raise UnsafeURLError("credentials in URL not allowed")
    try:
        port = parts.port
    except ValueError as e:
        raise UnsafeURLError("invalid port") from e
    if port not in (None, 80, 443):
        raise UnsafeURLError(f"port not allowed: {port}")

    try:
        infos = resolve(parts.hostname, port or DEFAULT_PORTS[parts.scheme], type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        raise UnsafeURLError(f"cannot resolve host: {parts.hostname}") from e

    # ponytail: validate-then-connect leaves a DNS-rebinding window; pin the resolved IP
    # in a custom transport before exposing the app beyond localhost.
    for *_, sockaddr in infos:
        ip = ipaddress.ip_address(sockaddr[0].split("%")[0])
        if ip.version == 6 and ip.ipv4_mapped:
            ip = ip.ipv4_mapped
        if not ip.is_global:
            raise UnsafeURLError(f"non-public address: {ip}")
