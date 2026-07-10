"""
TOBI Premium Ability (#14) — reader + capabilities + hermes test suite.

Isolated temp DB (DB_PATH env), plain python, no pytest:
    DB_PATH=/tmp/t14.db python tests/test_premium_readers.py

Covers: the model-capability registry (vision/reasoning/context + safe fallback +
model_router delegation), YouTube URL detection + cap + dedup, transcript fallback
(available / unavailable / dependency-missing), long-transcript summarize vs partial
excerpt, the chat reader context assembly (YouTube context included, honest notice on
failure, image fold-in note), and the read-only Hermes skill parser (3 repo files,
missing folder, malformed file).
"""
import os
import sys
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="tobi_t14_")
os.environ["DB_PATH"] = os.path.join(_TMP, "agent.db")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import init_database  # noqa: E402
from core import model_capabilities as mc  # noqa: E402
from core import model_router  # noqa: E402
from core import youtube_reader as yt  # noqa: E402
from core import premium_readers as pr  # noqa: E402
from core import hermes_skills as hs  # noqa: E402

PASS = 0


def ok(name: str, cond: bool, detail: str = ""):
    global PASS
    if not cond:
        print(f"❌ {name} {detail}")
        sys.exit(1)
    PASS += 1
    print(f"✅ {name}")


init_database()

# ── 1. Model capability registry ─────────────────────────────────────────────────
ok("vision: claude opus", mc.supports_vision("anthropic:claude-opus-4-8"))
ok("vision: gpt-4o", mc.supports_vision("openai:gpt-4o"))
ok("vision: gemini pro", mc.supports_vision("gemini:gemini-2.5-pro"))
ok("vision: grok-4", mc.supports_vision("grok:grok-4"))
ok("no-vision: nemotron", not mc.supports_vision("openrouter:nvidia/nemotron-3-super-120b-a12b:free"))
ok("no-vision: glm-4.6", not mc.supports_vision("glm:glm-4.6"))
ok("no-vision: grok-3", not mc.supports_vision("grok:grok-3"))
ok("no-vision: o3-mini", not mc.supports_vision("openai:o3-mini"))
ok("unknown model → safe fallback (no vision)", not mc.supports_vision("mystery:foo-bar-baz"))
ok("empty model → safe default", not mc.supports_vision(""))
ok("reasoning: o3-mini true", mc.supports_reasoning("openai:o3-mini"))
ok("reasoning: gpt-4o false", not mc.supports_reasoning("openai:gpt-4o"))
ok("context: gemini 1M", mc.context_window("gemini:gemini-2.5-pro") == 1000000)
ok("context: claude 200k", mc.context_window("anthropic:claude-opus-4-8") == 200000)
ok("router delegates to registry (vision)", model_router.supports_vision("openai:gpt-4o"))
ok("router delegates to registry (no vision)", not model_router.supports_vision("openrouter:nvidia/nemotron-3-super-120b-a12b:free"))

# ── 2. YouTube URL detection ─────────────────────────────────────────────────────
ok("detect watch url", yt.find_youtube_urls("see https://www.youtube.com/watch?v=dQw4w9WgXcQ ok")
   == ["https://www.youtube.com/watch?v=dQw4w9WgXcQ"])
ok("detect youtu.be", yt.find_youtube_urls("https://youtu.be/dQw4w9WgXcQ") == ["https://youtu.be/dQw4w9WgXcQ"])
ok("detect shorts", yt.find_youtube_urls("https://www.youtube.com/shorts/dQw4w9WgXcQ")
   == ["https://www.youtube.com/shorts/dQw4w9WgXcQ"])
ok("non-youtube ignored", yt.find_youtube_urls("read https://example.com/watch?v=nope") == [])
ok("dedup by video id", len(yt.find_youtube_urls(
    "https://youtu.be/dQw4w9WgXcQ and https://www.youtube.com/watch?v=dQw4w9WgXcQ")) == 1)
_multi = ("https://youtu.be/aaaaaaaaaaa https://youtu.be/bbbbbbbbbbb https://youtu.be/ccccccccccc")
ok("cap at MAX_LINKS", len(yt.find_youtube_urls(_multi)) == yt.MAX_LINKS)
ok("trailing punctuation trimmed", yt.youtube_id_in("watch (https://youtu.be/dQw4w9WgXcQ).") == "dQw4w9WgXcQ")

# ── 3. Transcript fallback (stubbed to avoid network) ─────────────────────────────
yt.fetch_youtube_meta = lambda url: {"title": "Stub Title", "author": "Stub Chan"}  # no network

yt._raw_transcript = lambda vid: (None, "no_dependency")
r = yt.read_youtube("https://youtu.be/dQw4w9WgXcQ")
ok("dep missing → not available", not r.available and r.reason == "no_dependency")
ok("dep missing → honest install note", "unavailable in this install" in r.note)

yt._raw_transcript = lambda vid: (None, "unavailable")
r = yt.read_youtube("https://youtu.be/dQw4w9WgXcQ")
ok("unavailable → honest note", not r.available and "could not read the transcript" in r.note)

r = yt.read_youtube("https://example.com/not-a-video")
ok("not youtube → reason", r.reason == "not_youtube" and not r.available)

yt._raw_transcript = lambda vid: ("This is a short faithful transcript about testing.", "")
r = yt.read_youtube("https://youtu.be/dQw4w9WgXcQ")
ok("available short transcript", r.available and "faithful transcript" in r.text and not r.summarized)
ok("context_block labelled", "[YouTube transcript context]" in yt.context_block(r) and "Video id: dQw4w9WgXcQ" in yt.context_block(r))

# long transcript → summarize
long_text = "word " * 4000  # > SUMMARIZE_OVER chars
yt._raw_transcript = lambda vid: (long_text, "")
yt._summarize = lambda text, title: "A tidy summary."
r = yt.read_youtube("https://youtu.be/dQw4w9WgXcQ")
ok("long transcript summarized", r.available and r.summarized and r.text == "A tidy summary.")
ok("summary block label", "Transcript summary:" in yt.context_block(r))

# long transcript, summarize fails → partial excerpt
yt._summarize = lambda text, title: None
r = yt.read_youtube("https://youtu.be/dQw4w9WgXcQ")
ok("summary fail → partial excerpt", r.available and r.partial and len(r.text) <= yt.EXCERPT_CHARS)
ok("partial block note", "partial" in yt.context_block(r).lower())

# ── 4. Premium reader context assembly ───────────────────────────────────────────
yt._raw_transcript = lambda vid: ("The talk covers three key ideas.", "")
res = pr.read_message("thoughts on https://youtu.be/dQw4w9WgXcQ ?")
ok("reader used", res.used and res.any_available)
ok("youtube context present", "[YouTube transcript context]" in res.youtube_context and "three key ideas" in res.youtube_context)
ctx = pr.compose_context("--- file.txt ---\nhello", res)
ok("compose merges att + youtube", "file.txt" in ctx and "[YouTube transcript context]" in ctx)

yt._raw_transcript = lambda vid: (None, "unavailable")
res2 = pr.read_message("summary of https://youtu.be/dQw4w9WgXcQ")
ok("unavailable → honest notice", res2.used and not res2.any_available and res2.notices)
ctx2 = pr.compose_context(None, res2)
ok("compose surfaces reader note", "Reader notes" in ctx2 and "could not read the transcript" in ctx2)

ok("no youtube → empty passthrough", not pr.read_message("just a normal message").used)
ok("image note honest", "vision-capable" in pr.image_unavailable_note(2))
note_ctx = pr.compose_context("body", pr.ReaderResult(), pr.image_unavailable_note(1))
ok("compose adds image note", "vision-capable" in note_ctx and "body" in note_ctx)
ok("notice payload shape", pr.notice_payload(res2)["kind"] == "reader" and "items" in pr.notice_payload(res2))

# rollback flag disables the whole layer
pr.ENABLE_PREMIUM_READERS = False
ok("rollback flag disables reader", not pr.read_message("https://youtu.be/dQw4w9WgXcQ").used)
pr.ENABLE_PREMIUM_READERS = True

# ── 5. Hermes skill parser (read-only) ───────────────────────────────────────────
report = hs.skills_report()
ok("parses 3 repo skill files", report["count"] == 3, str(report["count"]))
ids = {s["id"] for s in report["items"]}
ok("known skill ids present", {"skill_ceo_agent", "skill_self_improve", "skill_research_pm_learning"} <= ids)
ceo = next(s for s in report["items"] if s["id"] == "skill_ceo_agent")
ok("name from first heading", ceo["name"] == "CEO Agent Skill")
ok("description non-empty", bool(ceo["description"]))
ok("risk approval_required", ceo["risk_tier"] == "approval_required")
ok("execution disabled", ceo["can_execute"] is False)
ok("source is repo file", ceo["source"] == "hermes_repo_file" and ceo["file_path"].startswith("hermes_skills/"))
ok("has last_modified", ceo["last_modified"])

# missing folder → empty, no crash
_orig_dir = hs.SKILLS_DIR
hs.SKILLS_DIR = Path(_TMP) / "no_such_dir"
ok("missing folder → []", hs.list_skills() == [])

# malformed / heading-less file → graceful metadata
tmp_skills = Path(_TMP) / "skills"
tmp_skills.mkdir(parents=True, exist_ok=True)
(tmp_skills / "weird_one.md").write_text("```\nno heading, just a fence\n```\n", encoding="utf-8")
hs.SKILLS_DIR = tmp_skills
weird = hs.list_skills()
ok("malformed file still parsed", len(weird) == 1 and weird[0]["id"] == "weird_one")
ok("fallback name from filename", weird[0]["name"] == "Weird One")
ok("fallback status available", weird[0]["status"] == "available")
hs.SKILLS_DIR = _orig_dir

print(f"\n🎉 ALL {PASS} CHECKS PASSED")
