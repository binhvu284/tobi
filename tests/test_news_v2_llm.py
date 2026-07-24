"""Background content-LLM routing (#23 owner QA: "no crash content, use glm 5.2").

Plain python, isolated DB, every seam stubbed (no network, no spend). Proves the two
guarantees behind the fix for the Tool Discovery card that showed raw chain-of-thought:
  1. resolve_content_model picks the owner's CURRENT chat model, never the free tier.
  2. sanitize/complete REJECT leaked reasoning, so a bad model yields no card, not trash.
  3. clear_leaked_recaps self-heals recaps already stored as reasoning.
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("DB_PATH", str(Path(tempfile.mkdtemp()) / "llm.db"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.database import init_database, get_connection  # noqa: E402
from core.news import llm  # noqa: E402
from core.news.repository import _ensure_once  # noqa: E402
from core import model_router, chat_store  # noqa: E402

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


# The exact shape of garbage the owner saw: the model narrating our own prompt back.
LEAKED = ("We need to produce a spotlight using only the given material. Material: NAME, "
          "SOURCE, DESCRIPTION. Must not invent features, numbers, or claims. So we can "
          "only convey what's given. We cannot invent capabilities not in the material.")
GOOD = ("Taste-Skill gives your AI good taste and stops it generating boring, generic "
        "output.\n**Highlights**\n- Curates tone automatically\n- Drops in with no config\n"
        "**Best for:** builders shipping AI writing features.")

# ── 1. sanitize: keep real content, reject reasoning ──────────────────────────────────
ok("clean content passes through unchanged", llm.sanitize(GOOD) == GOOD)
ok("the exact leaked chain-of-thought is rejected", llm.sanitize(LEAKED) is None)
ok("<think> reasoning blocks are stripped before inspection",
   llm.sanitize("<think>let me plan this out, we need to...</think>\n" + GOOD) == GOOD)
ok("first-person planning (2+ markers) is rejected",
   llm.sanitize("We should list three points. We could add more. Here is the tool.") is None)
ok("empty / too-short output is rejected", llm.sanitize("") is None and llm.sanitize("ok.") is None)
ok("looks_leaked mirrors sanitize", llm.looks_leaked(LEAKED) and not llm.looks_leaked(GOOD))

# ── 2. resolve_content_model: the owner's CURRENT chat model, never :free ─────────────
_real_cfg, _real_sessions, _real_models = (
    model_router.load_llm_config, chat_store.list_sessions, model_router.available_models)

model_router.load_llm_config = lambda: {"default_model": "anthropic:claude-opus-4-8"}
ok("explicit config default wins", llm.resolve_content_model() == "anthropic:claude-opus-4-8")

model_router.load_llm_config = lambda: {"default_model": ""}
chat_store.list_sessions = lambda: [{"model": "glm:glm-5.2"}, {"model": "codex:gpt-5.6-sol"}]
ok("with no explicit default, the current chat session's model is used (glm 5.2)",
   llm.resolve_content_model() == "glm:glm-5.2")

chat_store.list_sessions = lambda: [{"model": None}, {"model": ""}]
model_router.available_models = lambda: [
    {"id": "openrouter/nemotron:free"}, {"id": "glm:glm-5.2"}, {"id": "anthropic:claude-opus-4-8"}]
ok("last resort is the best available NON-free model (glm preferred), never :free",
   llm.resolve_content_model() == "glm:glm-5.2")

model_router.available_models = lambda: [{"id": "openrouter/nemotron:free"}]
ok("when only free models exist, resolve returns '' → caller skips (no free-tier trash)",
   llm.resolve_content_model() == "")

# ── 3. complete: route to that model, then sanitize ───────────────────────────────────
class FakeClient:
    def __init__(self, text):
        self._text = text
    def complete(self, messages, system=None, max_tokens=2000):
        return self._text


model_router.load_llm_config = lambda: {"default_model": "glm:glm-5.2"}
seen = {}
def _fake_get_llm(task_type="default", model=None):
    seen["model"] = model
    return FakeClient(seen["reply"])
model_router.get_llm = _fake_get_llm

seen["reply"] = GOOD
ok("complete returns clean content on the resolved model",
   llm.complete("sys", "user", "feed_recap", 200) == GOOD and seen["model"] == "glm:glm-5.2")
seen["reply"] = LEAKED
ok("complete returns None when the model leaks reasoning (no crash content)",
   llm.complete("sys", "user", "feed_recap", 200) is None)

model_router.load_llm_config, chat_store.list_sessions, model_router.available_models = (
    _real_cfg, _real_sessions, _real_models)

# ── 3.5 ClaudeClient text extraction skips reasoning blocks (THE root cause of empty ──
# cards): GLM-5.2 returns a leading thinking block, and the old content[0].text raised on
# it → every background completion silently died. Pure static method, no SDK needed.
class _Block:
    def __init__(self, btype, **kw):
        self.type = btype
        for k, v in kw.items():
            setattr(self, k, v)


class _Resp:
    def __init__(self, content):
        self.content = content


_thinking = _Block("thinking", thinking="let me plan the answer…")
_answer = _Block("text", text="The real answer.")
ok("text comes from the TEXT block, never the leading thinking block",
   model_router.ClaudeClient._text_from(_Resp([_thinking, _answer])) == "The real answer.")
ok("a thinking-only response yields '' and never raises",
   model_router.ClaudeClient._text_from(_Resp([_thinking])) == "")
ok("a plain single text block still works",
   model_router.ClaudeClient._text_from(_Resp([_Block("text", text="hi")])) == "hi")

# ── 4. clear_leaked_recaps: self-heal already-stored garbage ──────────────────────────
conn = get_connection()
_ensure_once(conn)
now = "2026-07-24T00:00:00+00:00"


def _seed(url, itype, recap):
    conn.execute(
        "INSERT INTO news_items (url_hash, canonical_url, title, item_type, first_seen_at,"
        " recap, recap_at) VALUES (?,?,?,?,?,?,?)",
        (url, url, "t", itype, now, recap, now if recap else None))


_seed("u-leak", "tool", LEAKED)
_seed("u-good", "tool", GOOD)
_seed("u-article", "article", LEAKED)      # different type — untouched by a tool/repo sweep
conn.commit()
cleared = llm.clear_leaked_recaps(conn, ("tool", "repo"))
ok("only the leaked tool recap is nulled (good one + other types untouched)", cleared == 1)
ok("the leaked recap is now NULL (re-eligible for a good regeneration)",
   conn.execute("SELECT recap FROM news_items WHERE url_hash='u-leak'").fetchone()[0] is None
   and conn.execute("SELECT recap FROM news_items WHERE url_hash='u-good'").fetchone()[0] == GOOD
   and conn.execute("SELECT recap FROM news_items WHERE url_hash='u-article'").fetchone()[0] == LEAKED)
conn.close()

print(f"\nALL {PASS} CHECKS PASSED")
