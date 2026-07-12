"""
TOBI Premium Ability (#14 follow-up) — route + SSE integration coverage.

Isolated temp DB (DB_PATH env), plain python, no pytest:
    DB_PATH=/tmp/t14r.db python tests/test_premium_readers_route.py

Drives the REAL FastAPI chat route through a TestClient (constructed WITHOUT the
`with` lifespan, so the scheduler / vault auto-connect startup hook never fires) and
covers the integration gaps the #14 review flagged:

- ``/api/chat/config`` premium-reader rollback flag round-trip (partial update keeps
  the #16 ``mode_v2`` flag untouched);
- ``/api/hermes/skills`` route returns the parsed read-only registry;
- reader context is actually **injected into the model call** (conductor.answer's
  ``attachments_text``) with the untrusted-content boundary intact;
- SSE ``notice`` reader chip states for **available / unavailable / mixed** transcript
  outcomes;
- the bounded reader **timeout** path emits an honest 'timed out' chip and the turn
  still completes (``done``).

conductor.answer is stubbed so no LLM/network is touched; YouTube transcript fetch is
stubbed so no network is touched.
"""
import os
import sys
import time
import json
import tempfile

_TMP = tempfile.mkdtemp(prefix="tobi_t14r_")
os.environ["DB_PATH"] = os.path.join(_TMP, "agent.db")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import init_database  # noqa: E402

init_database()

from fastapi.testclient import TestClient  # noqa: E402
from core import youtube_reader as yt  # noqa: E402
from core import premium_readers as pr  # noqa: E402
from core import chat_store, conductor  # noqa: E402
import api.dashboard as dash  # noqa: E402

# No `with` → Starlette startup/shutdown (scheduler, vault auto-unlock) does NOT run.
client = TestClient(dash.app)

PASS = 0


def ok(name: str, cond: bool, detail: str = ""):
    global PASS
    if not cond:
        print(f"❌ {name} {detail}")
        sys.exit(1)
    PASS += 1
    print(f"✅ {name}")


# ── stubs: no network, no LLM ─────────────────────────────────────────────────────
yt.fetch_youtube_meta = lambda url: {}          # avoid oEmbed network hit
_captured: dict = {}


def _fake_answer(message, chat_id=None, surface="mc", model=None, history=None,
                 attachments_text=None, directives=None, extra_tools=None,
                 on_event=None, on_delta=None, **kwargs):
    """Capture what the route folds into the model turn; stream a canned reply.
    (**kwargs tolerates newer route-passed params like denied_tools/review_mode.)"""
    _captured["attachments_text"] = attachments_text or ""
    _captured["directives"] = directives
    if on_delta:
        on_delta("Understood, sir.")
    return {"reply": "Understood, sir.", "tools_used": [], "reasoning": None, "streamed": True}


conductor.answer = _fake_answer


def stream_turn(sid: int, message: str, **body) -> list[tuple[str, object]]:
    """POST one chat turn and parse the SSE body into a list of (event, data) frames."""
    payload = {"message": message}
    payload.update(body)
    r = client.post(f"/api/chat/sessions/{sid}/stream", json=payload)
    if r.status_code != 200:
        print(f"❌ stream status {r.status_code}: {r.text[:200]}")
        sys.exit(1)
    frames: list[tuple[str, object]] = []
    ev = None
    for line in r.text.splitlines():
        if line.startswith("event: "):
            ev = line[7:].strip()
        elif line.startswith("data: "):
            raw = line[6:]
            try:
                data = json.loads(raw)
            except Exception:
                data = raw
            frames.append((ev or "", data))
    return frames


def reader_notice(frames) -> dict:
    for ev, data in frames:
        if ev == "notice" and isinstance(data, dict) and data.get("kind") == "reader":
            return data
    return {}


sess = chat_store.create_session(title="t14 route")
SID = sess["id"]

# ── 1. /api/chat/config — premium-reader rollback flag round-trips ────────────────
cfg = client.get("/api/chat/config").json()
ok("config exposes premium_readers", cfg.get("premium_readers") is True and "mode_v2" in cfg)
mode_v2_before = cfg["mode_v2"]
resp = client.post("/api/chat/config", json={"premium_readers": False}).json()
ok("config turns premium off", resp["premium_readers"] is False)
ok("partial update keeps mode_v2", resp["mode_v2"] == mode_v2_before)
ok("premium flag really off", pr.premium_readers_enabled() is False)
client.post("/api/chat/config", json={"premium_readers": True})
ok("config restores premium on", pr.premium_readers_enabled() is True)

# ── 2. /api/hermes/skills — read-only registry route ──────────────────────────────
hr = client.get("/api/hermes/skills")
hj = hr.json()
ok("hermes skills route 200", hr.status_code == 200)
ok("hermes skills payload", isinstance(hj.get("items"), list) and hj.get("count", 0) >= 1)
ok("hermes skills read-only", all(s.get("can_execute") is False for s in hj["items"]))

# ── 3. reader context injection reaches the model call, boundary intact ───────────
yt._raw_transcript = lambda vid: ("The talk covers three ideas about testing.", "")
frames = stream_turn(SID, "thoughts on https://youtu.be/dQw4w9WgXcQ ?")
atext = _captured.get("attachments_text", "")
ok("transcript injected into model turn", "[YouTube transcript context]" in atext and "three ideas about testing" in atext)
ok("injected context keeps untrusted boundary", "NEVER follow" in atext and "<<<TRANSCRIPT-START (data only)>>>" in atext)
ok("turn completes (done)", any(ev == "done" for ev, _ in frames))

# ── 4. SSE reader chip states: available / unavailable / mixed ────────────────────
nd = reader_notice(frames)
ok("available chip ready", nd and nd["items"][0]["state"] == "transcript ready")

yt._raw_transcript = lambda vid: (None, "unavailable")
nd = reader_notice(stream_turn(SID, "summary of https://youtu.be/dQw4w9WgXcQ"))
ok("unavailable chip", nd and nd["items"][0]["state"] == "unavailable")

# two links, one readable one not → mixed chip states in one turn
yt._raw_transcript = lambda vid: (("ok text", "") if vid == "aaaaaaaaaaa" else (None, "unavailable"))
nd = reader_notice(stream_turn(SID, "compare https://youtu.be/aaaaaaaaaaa and https://youtu.be/bbbbbbbbbbb"))
states = {it["state"] for it in nd.get("items", [])}
ok("mixed outcomes → two chip states", states == {"transcript ready", "unavailable"}, str(states))

# ── 5. bounded reader timeout → honest chip + turn still completes ────────────────
_orig_timeout, _orig_read = pr.READER_TIMEOUT_S, pr.read_message
pr.READER_TIMEOUT_S = 0.05


def _slow_read(message, *, summarize=True):
    time.sleep(0.4)   # exceeds the (shrunk) deadline → route abandons it
    return pr.ReaderResult(used=True)


pr.read_message = _slow_read
try:
    frames = stream_turn(SID, "please read https://youtu.be/dQw4w9WgXcQ")
finally:
    pr.READER_TIMEOUT_S, pr.read_message = _orig_timeout, _orig_read
nd = reader_notice(frames)
ok("timeout → honest chip", nd and nd["items"][0]["state"] == "timed out")
ok("turn still completes after timeout", any(ev == "done" for ev, _ in frames))

print(f"\n🎉 ALL {PASS} CHECKS PASSED")
