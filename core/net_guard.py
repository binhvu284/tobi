"""
NET GUARD — SSRF-safe outbound HTTP for tool-driven page reads (#16 follow-up).

TOBI fetches web pages chosen by an LLM or a search engine (Deep Research sources, project
resource links). Those URLs are UNTRUSTED, so a naive ``requests.get()`` is an SSRF hole: a
poisoned search result could point at ``localhost``, a private-network service, or a cloud
metadata endpoint (``169.254.169.254``). This module centralises the defence:

- allow only ``http`` / ``https``;
- resolve the host and REJECT any private / loopback / link-local / reserved / multicast /
  unspecified address (blocks metadata IPs, RFC1918, 127.x, ::1, obfuscated decimal IPs…);
- follow redirects MANUALLY, re-validating every hop (a safe URL can 30x to a private one);
- cap the response body size and the per-request time.

The validated public address is pinned into the socket URL while the original hostname remains
the HTTP Host and TLS SNI/certificate identity. DNS cannot change between validation and connect.
Callers catch ``UnsafeURLError`` (and normal requests errors) and degrade.
"""
from __future__ import annotations

import ipaddress
import socket
from typing import Optional
from urllib.parse import urljoin, urlparse, urlunparse

ALLOWED_SCHEMES = ("http", "https")
DEFAULT_MAX_BYTES = 3_000_000     # 3 MB body cap
DEFAULT_TIMEOUT = 15              # per-request seconds
MAX_REDIRECTS = 4


class UnsafeURLError(ValueError):
    """Raised when a URL fails the SSRF safety policy."""


def _ip_is_public(ip: str) -> bool:
    """True only for a globally-routable address — everything internal is rejected."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return not (addr.is_private or addr.is_loopback or addr.is_link_local
                or addr.is_reserved or addr.is_multicast or addr.is_unspecified)


def _resolved_ips(host: str) -> list[str]:
    """Every address the host resolves to (host may itself be an IP literal). Resolving and
    checking the ACTUAL connect IPs also defeats decimal/octal/hex IP obfuscation tricks."""
    try:
        infos = socket.getaddrinfo(host, None)
    except (socket.gaierror, UnicodeError, OSError):
        return []
    return [info[4][0].split("%", 1)[0] for info in infos]   # strip any IPv6 zone id


def check_url(url: str) -> str:
    """Validate one URL against the SSRF policy → the URL if safe, else raise UnsafeURLError.
    Only the scheme + resolved host are checked (no request is made)."""
    _validated_target(url)
    return url


def _validated_target(url: str) -> tuple[object, list[str]]:
    """Validate and return the exact resolved addresses that the caller must connect to."""
    parsed = urlparse((url or "").strip())
    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise UnsafeURLError(f"scheme '{parsed.scheme}' not allowed")
    host = parsed.hostname
    if not host:
        raise UnsafeURLError("missing host")
    ips = _resolved_ips(host)
    if not ips:
        raise UnsafeURLError(f"host '{host}' did not resolve")
    for ip in ips:
        if not _ip_is_public(ip):
            raise UnsafeURLError(f"host '{host}' resolves to non-public address {ip}")
    return parsed, ips


def _pinned_get(url: str, ips: list[str], *, timeout: int, headers: dict):
    """Connect to a validated IP while retaining the hostname for Host, SNI and TLS checks."""
    import requests
    from requests.adapters import HTTPAdapter

    parsed = urlparse(url)
    host = parsed.hostname or ""
    default_port = 443 if parsed.scheme.lower() == "https" else 80
    port = parsed.port or default_port
    host_header = host if port == default_port else f"{host}:{port}"
    last_error = None
    for ip in ips:
        ip_netloc = f"[{ip}]" if ":" in ip else ip
        if port != default_port:
            ip_netloc += f":{port}"
        pinned_url = urlunparse(parsed._replace(netloc=ip_netloc))
        session = requests.Session()
        session.trust_env = False
        adapter = HTTPAdapter()
        if parsed.scheme.lower() == "https":
            adapter.init_poolmanager(10, 10, assert_hostname=host, server_hostname=host)
        session.mount(f"{parsed.scheme.lower()}://", adapter)
        try:
            response = session.get(pinned_url, timeout=timeout,
                                   headers={**headers, "Host": host_header},
                                   allow_redirects=False, stream=True)
            response._tobi_session = session
            return response
        except requests.RequestException as exc:
            last_error = exc
            session.close()
    if last_error:
        raise last_error
    raise UnsafeURLError(f"host '{host}' has no validated public address")


def is_safe_url(url: str) -> bool:
    try:
        check_url(url)
        return True
    except Exception:
        return False


def safe_get(url: str, *, timeout: int = DEFAULT_TIMEOUT, max_bytes: int = DEFAULT_MAX_BYTES,
             headers: Optional[dict] = None, max_redirects: int = MAX_REDIRECTS):
    """SSRF-safe GET: validates the URL and EVERY redirect hop, disables auto-redirect, and
    caps the body size. Returns a ``requests.Response`` whose (capped) body is already read,
    so ``r.text`` / ``r.content`` work. Raises UnsafeURLError for a policy violation."""
    hdrs = {"User-Agent": "Mozilla/5.0 TOBI"}
    if headers:
        hdrs.update(headers)
    current = url
    for _ in range(max_redirects + 1):
        _parsed, ips = _validated_target(current)
        r = _pinned_get(current, ips, timeout=timeout, headers=hdrs)
        if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("Location"):
            loc = r.headers["Location"]
            r.close()
            if getattr(r, "_tobi_session", None):
                r._tobi_session.close()
            current = urljoin(current, loc)
            continue
        chunks: list[bytes] = []
        total = 0
        try:
            for chunk in r.iter_content(8192):
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    break
                chunks.append(chunk)
        finally:
            r.close()
            if getattr(r, "_tobi_session", None):
                r._tobi_session.close()
        r._content = b"".join(chunks)                          # capped body for r.text/.content
        r._content_consumed = True
        return r
    raise UnsafeURLError("too many redirects")
