"""News V2 media pipeline (#23) — SSRF guards + caching. Plain python, isolated DB.

Proves the security contract the owner's image feature depends on: private/loopback
hosts are refused, redirects are not followed, non-image and oversized responses are
rejected, and a successful fetch caches once (idempotent). No real network — the
HTTP layer and DNS resolution are stubbed.
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("DB_PATH", str(Path(tempfile.mkdtemp()) / "media.db"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.database import init_database, get_connection  # noqa: E402
from core.news import media  # noqa: E402

init_database()
PASS = 0


def ok(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print(f"PASS {name}")
    else:
        print(f"FAIL {name} {detail}")
        raise SystemExit(1)


# ── host classification: fail closed on anything non-public ──────────────────────────
_public = {"cdn.example.com": "93.184.216.34"}
_private = {
    "localhost": "127.0.0.1", "internal": "10.0.0.5", "meta": "169.254.169.254",
    "lan": "192.168.1.10", "unique-local": "fd00::1",
}


def fake_getaddrinfo(host, *_a, **_k):
    if host in _public:
        return [(2, 1, 6, "", (_public[host], 0))]
    if host in _private:
        return [(2, 1, 6, "", (_private[host], 0))]
    import socket
    raise socket.gaierror("unknown host")


media.socket.getaddrinfo = fake_getaddrinfo

ok("public unicast host is allowed", media._host_is_public("cdn.example.com"))
for bad in _private:
    ok(f"non-public host refused: {bad}", not media._host_is_public(bad))
ok("unresolvable host refused", not media._host_is_public("nope.invalid"))
ok("empty host refused", not media._host_is_public(""))


# ── download guards: scheme, redirects, mime, size ───────────────────────────────────
class FakeResp:
    def __init__(self, status=200, headers=None, chunks=(b"imgbytes",)):
        self.status_code = status
        self.headers = headers or {"Content-Type": "image/png"}
        self._chunks = chunks

    def iter_content(self, _n):
        return iter(self._chunks)

    def close(self):
        pass


class FakeRequests:
    def __init__(self, resp):
        self._resp = resp
        self.calls = []

    def get(self, url, **kw):
        self.calls.append((url, kw))
        return self._resp


def with_requests(resp):
    fake = FakeRequests(resp)
    sys.modules["requests"] = fake  # media imports requests lazily inside _download
    return fake


ok("javascript: scheme refused before any fetch", media._download("javascript:alert(1)") is None)
ok("private host refused before any fetch", media._download("http://localhost/x.png") is None)

fake = with_requests(FakeResp())
got = media._download("https://cdn.example.com/a.png")
ok("valid public image downloads", got == (b"imgbytes", "image/png"))
ok("download disables redirect following (SSRF via 3xx)", fake.calls[-1][1].get("allow_redirects") is False)

with_requests(FakeResp(status=302, headers={"Location": "http://10.0.0.5/x"}))
ok("a redirect response is refused, never followed", media._download("https://cdn.example.com/r.png") is None)

with_requests(FakeResp(headers={"Content-Type": "text/html"}))
ok("non-image content-type refused", media._download("https://cdn.example.com/page.html") is None)

with_requests(FakeResp(headers={"Content-Type": "image/png", "Content-Length": str(media.MAX_BYTES + 1)}))
ok("oversized (declared) refused", media._download("https://cdn.example.com/big.png") is None)

with_requests(FakeResp(chunks=(b"x" * (media.MAX_BYTES + 10),)))
ok("oversized (streamed past the cap) refused", media._download("https://cdn.example.com/lie.png") is None)


# ── cache_image: writes once, serves the key, idempotent ─────────────────────────────
conn = get_connection()
with_requests(FakeResp(chunks=(b"PNGDATA",)))
key = media.cache_image(conn, "https://cdn.example.com/thumb.png")
ok("cache_image returns a served key", bool(key) and key.endswith(".png"))
ok("bytes are written to the media dir", (media.media_dir() / key).is_file())
row = conn.execute("SELECT bytes, mime FROM news_media_cache").fetchone()
ok("cache row records the image", row is not None and row[1] == "image/png")

fake2 = with_requests(FakeResp(chunks=(b"SHOULD-NOT-REFETCH",)))
key2 = media.cache_image(conn, "https://cdn.example.com/thumb.png")
ok("second call is a cache hit (no refetch)", key2 == key and not fake2.calls)

with_requests(FakeResp(headers={"Content-Type": "text/html"}))
ok("a failed fetch returns None (item just has no thumbnail)",
   media.cache_image(conn, "https://cdn.example.com/broken") is None)
conn.close()

print(f"\nALL {PASS} CHECKS PASSED")
