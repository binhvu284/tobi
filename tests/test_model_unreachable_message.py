"""A model TOBI never reached must not be reported as a model that answered badly.

On 2026-08-20 the owner ran the #21 main-gate owner test. Chat replied, every time:

    The current model is struggling
    It kept returning incomplete output, sir. Switch to a stronger model and I'll
    pick this straight back up.

The model was not struggling. It was never contacted. The Mission Control process had
been started inside a sandbox with no outbound network, so every provider call raised
`APIConnectionError("Connection error.")`. `generate_step` swallowed the exception into
an empty string, the loop counted three empties, and the composer escalated to a second
provider that also could not be reached. The transport failure was erased on the way up,
so the one fact that would have ended the session in a minute -- *the request never left
the machine* -- reached nobody, and the owner was sent to the model picker instead. Two
test runs were lost to it.

CLAUDE.md: "Error messages must be true and actionable." An empty reply from a provider
that answered and an empty reply from a provider that was never reached are different
failures with different fixes, and the owner must be told which one he has.

The rule this suite enforces: when no model call in a turn ever reached a provider, the
owner is told that, with a bounded reason, and is not told to switch models. When a model
really did answer with garbage, the existing struggling notice is unchanged.

Isolated temp DB, plain python, no pytest:
    python tests/test_model_unreachable_message.py
"""
import os
import pathlib
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix="tobi_unreachable_")
os.environ["DB_PATH"] = os.path.join(_TMP, "agent.db")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import init_database  # noqa: E402

init_database()

from core import conductor  # noqa: E402
from core import model_router as mr  # noqa: E402
from core import task_classifier as tc  # noqa: E402
from core.runtime import transport_failure  # noqa: E402

tc.classify = lambda m: "QUESTION"  # force the tool loop, not SMALLTALK/CODING

FAILURES: list[str] = []


def ok(name: str, cond: bool, detail: str = "") -> None:
    print(f"{'PASS' if cond else 'FAIL'} {name}{('  -> ' + detail) if detail and not cond else ''}")
    if not cond:
        FAILURES.append(name)


# The provider bodies real clients raise carry things the owner must never see in Chat.
SECRET_BODY = (
    "Connection error. url=https://api.example.com/v1/responses "
    "authorization=Bearer sk-live-DO-NOT-LEAK-284 trace=/home/owner/.codex/auth.json"
)


class _APIConnectionError(Exception):
    """Shaped like the SDK error: the class name is what identifies the failure."""


class _AuthenticationError(Exception):
    pass


class _Unreachable:
    """A provider that is never reached. Both call paths raise, as they do live."""

    last_finish_reason = None

    def __init__(self, exc_type=_APIConnectionError, message=SECRET_BODY, streaming=False):
        self.exc_type = exc_type
        self.message = message
        self.calls = 0
        if streaming:
            self.complete_stream = self._stream

    def complete(self, messages, system=None, max_tokens=2000):
        self.calls += 1
        raise self.exc_type(self.message)

    def _stream(self, messages, system=None, max_tokens=2000):
        self.calls += 1
        raise self.exc_type(self.message)
        yield ""  # pragma: no cover - generator shape only


class _Garbage:
    """A provider that IS reached and answers with an unusable tool call forever."""

    last_finish_reason = "stop"

    def complete(self, messages, system=None, max_tokens=2000):
        return '{"tool":'


def reply_of(res: dict) -> str:
    return res.get("reply", "") or ""


# --- 1. the live failure: nothing reachable, non-streaming path -------------------------
client = _Unreachable()
mr.get_llm = lambda *a, **k: client
mr.get_escalation_llm = lambda *a, **k: (_Unreachable(), "openrouter:openai/gpt-5.6-sol-pro")
res = conductor.answer("Reply with exactly: RUNTIME V2 ACTIVE", chat_id=-9301, surface="mc")
reply = reply_of(res)

ok("the owner is not told to switch to a stronger model",
   "stronger model" not in reply.lower(), reply[:200])
ok("the owner is not told the model was struggling",
   "struggling" not in reply.lower(), reply[:200])
ok("the owner is told the model was never reached",
   "never reached" in reply.lower(), reply[:200])
ok("the turn is still reported as a failure",
   res.get("model_issue") is True, str(res.get("model_issue")))
ok("the failure carries a bounded transport reason",
   res.get("model_unreachable") == "unreachable", str(res.get("model_unreachable")))
ok("the raw provider body never reaches the owner",
   "sk-live" not in reply and "api.example.com" not in reply and "auth.json" not in reply,
   reply[:200])

# --- 2. same failure on the streaming path ---------------------------------------------
streamed: list[str] = []
mr.get_llm = lambda *a, **k: _Unreachable(streaming=True)
mr.get_escalation_llm = lambda *a, **k: (_Unreachable(streaming=True), "openrouter:x-ai/grok-4.5")
res2 = conductor.answer("Reply with exactly: RUNTIME V2 ACTIVE", chat_id=-9302, surface="mc",
                        on_delta=streamed.append)
reply2 = reply_of(res2)

ok("a streamed turn that never reached a provider says so",
   "never reached" in reply2.lower() and "stronger model" not in reply2.lower(), reply2[:200])
ok("a streamed turn carries the transport reason too",
   res2.get("model_unreachable") == "unreachable", str(res2.get("model_unreachable")))
ok("nothing raw was streamed to the screen",
   "sk-live" not in "".join(streamed), "".join(streamed)[:160])

# --- 3. a rejected credential is a different fact, and says so --------------------------
mr.get_llm = lambda *a, **k: _Unreachable(exc_type=_AuthenticationError, message="401 invalid api key")
mr.get_escalation_llm = lambda *a, **k: (None, None)
res3 = conductor.answer("status?", chat_id=-9303, surface="mc")
reply3 = reply_of(res3)

ok("a rejected credential is reported as a credential problem",
   res3.get("model_unreachable") == "auth", str(res3.get("model_unreachable")))
ok("and points at the key, not the model picker",
   "key" in reply3.lower() and "stronger model" not in reply3.lower(), reply3[:200])

# --- 4. no false positive: a model that really did answer badly is unchanged ------------
mr.get_llm = lambda *a, **k: _Garbage()
mr.get_escalation_llm = lambda *a, **k: (None, None)
res4 = conductor.answer("list projects", chat_id=-9304, surface="mc")
reply4 = reply_of(res4)

ok("a reachable model that answers badly is still a model issue",
   res4.get("model_issue") is True, str(res4.get("model_issue")))
ok("and still gets the struggling notice",
   "struggling" in reply4.lower() or "stronger model" in reply4.lower(), reply4[:200])
ok("and is not mislabelled as unreachable",
   not res4.get("model_unreachable"), str(res4.get("model_unreachable")))

# --- 5. the classifier itself: bounded codes, no raw text -------------------------------
ok("a connection error classifies as unreachable",
   transport_failure.classify(_APIConnectionError(SECRET_BODY)) == "unreachable")
ok("a builtin connection error classifies too",
   transport_failure.classify(ConnectionResetError("reset by peer")) == "unreachable")
ok("a timeout classifies as timeout",
   transport_failure.classify(TimeoutError("timed out")) == "timeout")
ok("an auth error classifies as auth",
   transport_failure.classify(_AuthenticationError("401")) == "auth")
ok("an unrecognised failure still classifies as something",
   transport_failure.classify(ValueError("who knows")) == "unknown")
ok("every code has an owner message that names no raw detail",
   all(SECRET_BODY not in transport_failure.owner_message(code)
       and "stronger model" not in transport_failure.owner_message(code).lower()
       for code in transport_failure.CODES))

# --- 6. the card the owner actually reads ----------------------------------------------
# The backend can be perfectly honest and the owner still read "switch to a stronger model",
# because that copy is hardcoded in the Chat card. Both halves have to agree or the fix is
# invisible where it matters.
_CHAT = (pathlib.Path(__file__).resolve().parents[1] / "dashboard" / "src" / "pages" / "Chat.tsx"
         ).read_text(encoding="utf-8")

ok("Chat keeps the reason the server sent", "setModelUnreachable(n.detail" in _CHAT)
ok("the model picker is not offered when no model was reachable",
   "{!modelUnreachable && <ModelMenu" in _CHAT)
ok("the card shows the server's sentence instead of the struggling copy",
   "{modelUnreachable || 'It kept returning incomplete output" in _CHAT)

print(f"\n{'ALL' if not FAILURES else str(len(FAILURES)) + ' OF'} "
      f"{'MODEL-UNREACHABLE CHECKS PASSED' if not FAILURES else 'CHECKS FAILED: ' + ', '.join(FAILURES)}")
raise SystemExit(1 if FAILURES else 0)
