"""
NET GUARD — SSRF policy for tool-driven page fetches (#16 follow-up).

Plain python, no pytest, no network (IP literals resolve without DNS; a fake requests
module drives the redirect/size-cap paths):
    python tests/test_net_guard.py

Covers: scheme allowlist, rejection of loopback/private/link-local/reserved/multicast/
metadata addresses (incl. 'localhost' and obfuscated decimal IPs), a public host passing,
redirect re-validation (a safe URL that 302s to a private one is blocked), and the body
size cap.
"""
import os
import sys
import tempfile

os.environ.setdefault("DB_PATH", os.path.join(tempfile.mkdtemp(prefix="tobi_netg_"), "agent.db"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:  # keep the ✅/❌ glyphs printable on a legacy Windows code page
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from core import net_guard as ng  # noqa: E402

PASS = 0


def ok(name: str, cond: bool, detail: str = ""):
    global PASS
    if not cond:
        print(f"❌ {name} {detail}")
        sys.exit(1)
    PASS += 1
    print(f"✅ {name}")


# ── scheme + host policy ──────────────────────────────────────────────────────────
ok("rejects file scheme", not ng.is_safe_url("file:///etc/passwd"))
ok("rejects ftp scheme", not ng.is_safe_url("ftp://example.com/x"))
ok("rejects gopher scheme", not ng.is_safe_url("gopher://x/"))
ok("rejects missing host", not ng.is_safe_url("http:///nohost"))

# ── loopback / private / link-local / reserved / metadata (IP literals — no DNS) ──
ok("rejects 127.0.0.1", not ng.is_safe_url("http://127.0.0.1/"))
ok("rejects ::1 loopback", not ng.is_safe_url("http://[::1]/"))
ok("rejects 10.x private", not ng.is_safe_url("http://10.0.0.5/"))
ok("rejects 192.168.x private", not ng.is_safe_url("http://192.168.1.1:8080/admin"))
ok("rejects 172.16.x private", not ng.is_safe_url("http://172.16.0.1/"))
ok("rejects cloud metadata 169.254.169.254", not ng.is_safe_url("http://169.254.169.254/latest/meta-data/"))
ok("rejects 0.0.0.0 unspecified", not ng.is_safe_url("http://0.0.0.0/"))
ok("rejects localhost name", not ng.is_safe_url("http://localhost:8080/"))
ok("rejects obfuscated decimal IP", not ng.is_safe_url("http://2130706433/"))  # = 127.0.0.1

# ── a public host passes (8.8.8.8 is a global literal — parses without DNS) ────────
ok("allows public IP literal", ng.is_safe_url("http://8.8.8.8/"))
ok("allows https public IP literal", ng.is_safe_url("https://1.1.1.1/"))
ok("check_url returns url on safe", ng.check_url("https://8.8.8.8/x") == "https://8.8.8.8/x")
try:
    ng.check_url("http://127.0.0.1/")
    ok("check_url raises on unsafe", False)
except ng.UnsafeURLError:
    ok("check_url raises on unsafe", True)


# ── safe_get: redirect re-validation + body size cap (fake requests, no network) ──
class _FakeResp:
    def __init__(self, status, headers=None, body=b"", location=None):
        self.status_code = status
        self.headers = dict(headers or {})
        if location:
            self.headers["Location"] = location
        self._body = body
        self._content = False
        self._content_consumed = False

    def iter_content(self, n):
        for i in range(0, len(self._body), n):
            yield self._body[i:i + n]

    def close(self):
        pass

    @property
    def content(self):
        return self._content if self._content is not False else self._body

    @property
    def text(self):
        return self.content.decode("utf-8", errors="replace")


class _FakeRequests:
    class compat:
        @staticmethod
        def urljoin(base, url):
            from urllib.parse import urljoin
            return urljoin(base, url)

    def __init__(self, script):
        self.script = list(script)
        self.calls: list[str] = []

    def get(self, url, **kw):
        self.calls.append(url)
        return self.script.pop(0)


def _with_fake_requests(fake, fn):
    previous = ng._pinned_get
    ng._pinned_get = lambda url, ips, *, timeout, headers: fake.get(
        url, timeout=timeout, headers=headers, allow_redirects=False, stream=True)
    try:
        return fn()
    finally:
        ng._pinned_get = previous


# a safe URL that 302-redirects to a private host must be blocked at the next hop
fake = _FakeRequests([_FakeResp(302, location="http://127.0.0.1/")])
try:
    _with_fake_requests(fake, lambda: ng.safe_get("http://8.8.8.8/"))
    ok("redirect to private host blocked", False)
except ng.UnsafeURLError:
    ok("redirect to private host blocked", True)
ok("redirect hop was validated (one request made)", fake.calls == ["http://8.8.8.8/"])

# body size cap: a 20 KB page fetched with a 10 KB cap returns a truncated body
big = _FakeRequests([_FakeResp(200, headers={"content-type": "text/html"}, body=b"a" * 20000)])
r = _with_fake_requests(big, lambda: ng.safe_get("http://8.8.8.8/", max_bytes=10000))
ok("body capped at max_bytes", 0 < len(r.content) <= 10000, str(len(r.content)))

# Validation and connect share one DNS answer; a second lookup cannot rebind the socket target.
resolve_calls = []
old_resolve = ng._resolved_ips
old_pinned = ng._pinned_get
ng._resolved_ips = lambda host: resolve_calls.append(host) or ["8.8.8.8"]
ng._pinned_get = lambda url, ips, **kw: (_FakeResp(200, body=b"ok")
                                        if ips == ["8.8.8.8"] else (_ for _ in ()).throw(AssertionError(ips)))
try:
    ng.safe_get("http://example.test/")
    ok("DNS answer pinned without re-resolution", resolve_calls == ["example.test"], str(resolve_calls))
finally:
    ng._resolved_ips = old_resolve
    ng._pinned_get = old_pinned

# Drive classification must be hostname-based; an attacker cannot smuggle a marker in the path.
from core import pm_resources as pmr
ok("drive host classified exactly", pmr.classify_url("https://docs.google.com/document/d/abc")[0] == "drive")
ok("drive substring on attacker host rejected",
   pmr.classify_url("http://127.0.0.1/?next=docs.google.com/document")[0] == "web")

seen_drive = []
old_safe_get = ng.safe_get
ng.safe_get = lambda url, **kw: seen_drive.append(url) or _FakeResp(
    200, headers={"content-type": "text/html"}, body=b'<meta property="og:title" content="Safe Doc">')
try:
    ok("drive metadata uses guarded fetch",
       pmr.fetch_gdrive_meta("https://docs.google.com/document/d/abc") == "Safe Doc" and len(seen_drive) == 1)
    ok("non-drive metadata fails closed",
       pmr.fetch_gdrive_meta("http://127.0.0.1/?docs.google.com/document") is None and len(seen_drive) == 1)
finally:
    ng.safe_get = old_safe_get

print(f"\n🎉 ALL {PASS} CHECKS PASSED")
