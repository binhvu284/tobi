"""The Codex client must speak the dialect of whichever backend it reached.

`CodexClient` targets two endpoints that share the Responses API but not its rules. The
platform API (`api.openai.com`) accepts an ordinary non-streaming call with
`max_output_tokens`. The ChatGPT subscription backend (`chatgpt.com/backend-api/codex`)
rejects all three of those defaults:

    store=true            -> 400 "Store must be set to false"
    non-streaming         -> 400 "Stream must be set to true"
    max_output_tokens=... -> 400 "Unsupported parameter: max_output_tokens"

Only the platform dialect was ever sent, so every in-process Codex call failed on a
subscription — which is what stalled acceptance review on run 16. The 400 surfaced as
`AuthenticationError` while the token was valid for another 92 hours and the account id was
present, sending the diagnosis after credentials that were never the problem.

The Codex *CLI* worker was unaffected: it is a separate binary that builds its own requests.
Only the library client used by the reviewer carried the bug, which is why implementer sprints
kept succeeding while review could not start.

No live API call is made here; these assert the request that would be sent.
"""
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.llm_clients.codex import CodexClient  # noqa: E402

FAILURES: list[str] = []


def ok(label: str, condition: bool, detail: str = "") -> None:
    print(f"{'PASS' if condition else 'FAIL'} {label}{('  -> ' + detail) if detail and not condition else ''}")
    if not condition:
        FAILURES.append(label)


def client_for(base_url: str) -> CodexClient:
    """A client with its transport left unbuilt -- only request shaping is under test."""
    instance = CodexClient.__new__(CodexClient)
    instance.base_url = base_url
    instance.model = "gpt-5.6-sol"
    return instance


subscription = client_for(CodexClient.SUBSCRIPTION_BASE)
platform = client_for(CodexClient.API_BASE)

ok("the subscription backend is recognised", subscription.on_subscription)
ok("the platform API is not mistaken for it", not platform.on_subscription)

messages = [{"role": "user", "content": "hello"}]

sub = subscription._request_kwargs(messages, "be brief", 2000, stream=False)
ok("subscription: store is explicitly false", sub.get("store") is False, str(sub.get("store")))
ok("subscription: the call streams even when the caller wanted one shot",
   sub.get("stream") is True, str(sub.get("stream")))
ok("subscription: max_output_tokens is omitted, not passed as None",
   "max_output_tokens" not in sub, str(sub.keys()))
ok("subscription: the system prompt still rides as instructions",
   sub.get("instructions") == "be brief")

api = platform._request_kwargs(messages, "be brief", 1234, stream=False)
ok("platform: the token budget is honoured", api.get("max_output_tokens") == 1234)
ok("platform: store is left at the API default", "store" not in api)
ok("platform: a one-shot call is not forced into streaming", "stream" not in api)

api_stream = platform._request_kwargs(messages, None, 1234, stream=True)
ok("platform: an explicit stream request is respected", api_stream.get("stream") is True)
ok("platform: no instructions key when no system prompt", "instructions" not in api_stream)

# Both dialects must still describe the same conversation.
for label, kwargs in (("subscription", sub), ("platform", api)):
    ok(f"{label}: the message survives conversion",
       kwargs["input"][0]["content"][0]["text"] == "hello", str(kwargs["input"])[:120])
    ok(f"{label}: the model is named", kwargs["model"] == "gpt-5.6-sol")


# --- accumulating a stream ---------------------------------------------------------------
class _Event:
    def __init__(self, type_: str, **kw) -> None:
        self.type = type_
        for key, value in kw.items():
            setattr(self, key, value)


class _Usage:
    input_tokens, output_tokens = 13, 5


class _Response:
    usage, status = _Usage(), "completed"


text, usage, status = subscription._consume([
    _Event("response.created"),
    _Event("response.output_text.delta", delta="o"),
    _Event("response.output_text.delta", delta="k"),
    _Event("response.completed", response=_Response()),
])
ok("a streamed reply is reassembled in order", text == "ok", repr(text))
ok("usage survives the stream", getattr(usage, "input_tokens", None) == 13)
ok("status survives the stream", status == "completed")

incomplete_text, _, incomplete_status = subscription._consume([
    _Event("response.output_text.delta", delta="partial"),
    _Event("response.incomplete", response=_Response()),
])
ok("a truncated reply still returns what arrived", incomplete_text == "partial")
ok("a non-completed terminal event is not ignored", incomplete_status == "completed",
   str(incomplete_status))

ok("an empty stream yields empty text, not None", subscription._consume([])[0] == "")

# --- the two paths share one shaper ------------------------------------------------------
source = (ROOT / "core" / "llm_clients" / "codex.py").read_text(encoding="utf-8")
stream_fn = source[source.index("def complete_stream"):][:600]
ok("complete_stream asks the shared shaper instead of rebuilding the request",
   "_request_kwargs(" in stream_fn and '"max_output_tokens": max_tokens' not in stream_fn,
   stream_fn[:200])
complete_fn = source[source.index("def complete("):source.index("def complete_stream")]
ok("complete asks the shared shaper too", "_request_kwargs(" in complete_fn)

print(f"\n{'ALL' if not FAILURES else str(len(FAILURES)) + ' OF'} "
      f"{'CODEX BACKEND CHECKS PASSED' if not FAILURES else 'CHECKS FAILED: ' + ', '.join(FAILURES)}")
raise SystemExit(1 if FAILURES else 0)
