"""Recovery must work for an owner who has configured nothing.

When a model returns output Chat cannot use, the Conductor is supposed to hand off to a second
model. `get_escalation_llm` read exactly two things: `cfg["fallback"]`, which ships empty, and
`cfg["default_model"]`, which is by definition the model that just failed and is skipped. So on
a stock install the handoff returned `(None, None)` every time -- a safety net with no rope, and
nothing anywhere said so.

The owner hit this on 2026-08-01, was told "try a stronger model from the picker", enabled a
second provider, and got the identical failure -- because provider enablement is not what that
function reads. The only fix available to him was to know that a hidden `fallback` list exists
and what to put in it.

His standard, set the same day: a feature that needs hidden configuration to work is broken,
not configurable. Escalation must find a working second model on its own.

Isolated, no network, no DB:
    python tests/test_escalation_without_config.py
"""
from __future__ import annotations

import os
import sys
import tempfile

os.environ.setdefault("DB_PATH", os.path.join(tempfile.mkdtemp(prefix="tobi_esc_"), "agent.db"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import model_router as mr  # noqa: E402

FAILURES: list[str] = []


def ok(name: str, cond: bool, detail: str = "") -> None:
    print(f"{'PASS' if cond else 'FAIL'} {name}{('  -> ' + detail) if detail and not cond else ''}")
    if not cond:
        FAILURES.append(name)


def _cfg(**over) -> dict:
    """A stock install: nothing configured beyond the model the owner picked."""
    base = {
        "default_model": "codex:gpt-5.6-sol",
        "task_overrides": {},
        "fallback": [],
        "providers": {},
    }
    base.update(over)
    return base


_built: list[str] = []


def _fake_build(model_id, cfg=None, **kw):
    """Stand in for build_client: construct without touching a network or an SDK."""
    _built.append(model_id)
    provider = model_id.split(":", 1)[0] if ":" in model_id else ""
    if provider in ("openai", "anthropic", "openrouter", "gemini", "grok", "glm"):
        raise mr.ModelProviderDisabled(f"{provider} is disabled.")
    return object()


mr.build_client = _fake_build

# --- 1. the reported failure: stock config, nothing set -----------------------------------
mr.load_llm_config = lambda: _cfg()
_built.clear()
client, model = mr.get_escalation_llm("codex:gpt-5.6-sol")
ok("a stock install still has somewhere to escalate to", client is not None,
   f"returned {model!r} after trying {_built}")
ok("escalation never returns the model that just failed", model != "codex:gpt-5.6-sol", str(model))
ok("the substitute comes from a provider that is not disabled",
   model is None or not model.startswith(("openai:", "anthropic:", "glm:")), str(model))

# --- 2. enabling another provider is not required, but must not break it -------------------
mr.load_llm_config = lambda: _cfg(providers={"glm": {"enabled": True}})
client2, model2 = mr.get_escalation_llm("codex:gpt-5.6-sol")
ok("still resolves when an unrelated provider is enabled", client2 is not None, str(model2))

# --- 3. an owner who DID configure a fallback keeps full control ---------------------------
mr.load_llm_config = lambda: _cfg(fallback=["codex:gpt-5.6-terra"])
client3, model3 = mr.get_escalation_llm("codex:gpt-5.6-sol")
ok("an explicit fallback still wins", model3 == "codex:gpt-5.6-terra", str(model3))

# --- 4. no false positive: never hand back the current model under another spelling ---------
mr.load_llm_config = lambda: _cfg(fallback=["codex:gpt-5.6-sol"])
client4, model4 = mr.get_escalation_llm("codex:gpt-5.6-sol")
ok("a fallback identical to the current model is skipped", model4 != "codex:gpt-5.6-sol", str(model4))

# --- 5. a provider with exactly one model has no sibling to offer, and must say so ----------
mr.load_llm_config = lambda: _cfg(default_model="ollama:solo")
ok("an unknown single-model provider degrades quietly, not loudly",
   mr.get_escalation_llm("ollama:solo")[0] is None
   or mr.get_escalation_llm("ollama:solo")[1] != "ollama:solo")

# --- 6. the transport retry chain has the same empty-by-default trap ----------------------
# get_llm() builds a FallbackClient from cfg["fallback"] too, so on a stock install every model
# call in TOBI had exactly one attempt: a single provider hiccup failed the whole request.
mr.load_llm_config = lambda: _cfg()
chain = mr.get_llm("default")
clients = getattr(chain, "clients", None) or getattr(chain, "_clients", None) or []
ok("a stock install gets more than one transport attempt", len(clients) > 1,
   f"chain length {len(clients)}")
ok("the retry chain respects MAX_TRANSPORT_ATTEMPTS", len(clients) <= mr.MAX_TRANSPORT_ATTEMPTS,
   f"chain length {len(clients)} > cap {mr.MAX_TRANSPORT_ATTEMPTS}")

print(f"\n{'ALL' if not FAILURES else str(len(FAILURES)) + ' OF'} "
      f"{'ESCALATION CHECKS PASSED' if not FAILURES else 'CHECKS FAILED: ' + ', '.join(FAILURES)}")
raise SystemExit(1 if FAILURES else 0)
