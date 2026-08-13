"""T09 Run 1: delivered #20 memory adapts into canonical Runtime context.

Plain Python, no pytest and no network:
    python tests/test_mc_runtime_owner_intelligence.py
"""
from __future__ import annotations

import inspect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.runtime import owner_intelligence  # noqa: E402
from core.runtime.contracts import (  # noqa: E402
    Certainty,
    ContextSourceType,
    RuntimeContextItem,
    TrustClass,
)


FAILURES: list[str] = []


def ok(name: str, condition: bool, detail: str = "") -> None:
    print(f"{'PASS' if condition else 'FAIL'} {name}")
    if not condition:
        if detail:
            print(f"  {detail}")
        FAILURES.append(name)


def memory(mid: int, **overrides):
    value = {
        "memory_id": mid,
        "text": f"Memory {mid}",
        "behavior_implication": "Keep the response concise.",
        "type": "preference",
        "authority": "soft",
        "scope": "global",
        "hedged": False,
        "precedence": 6,
        "score": 0.8,
        "signals": {"recency": 0.9},
        "chip": {
            "memory_id": mid,
            "text": f"Memory {mid}",
            "type": "preference",
            "scope": "global",
            "confidence": 0.95,
            "quality": 90.0,
            "hedged": False,
            "evidence": "owner",
        },
        "status": "active",
        "sensitive": False,
        "redacted": False,
        "trust": "trusted",
        "explicitness": "explicit",
        "updated_at": "2026-08-13T00:00:00+00:00",
        "provenance_refs": ("conversation:42",),
        "tags": ("response:concise",),
        "suggested_usage": "response",
    }
    value.update(overrides)
    return value


ok("Runtime context item is immutable", RuntimeContextItem.__dataclass_params__.frozen)
ok("owner-intelligence result is immutable", owner_intelligence.OwnerIntelligence.__dataclass_params__.frozen)

adapted = owner_intelligence.adapt_retrieval([memory(1)], mode="chat")
ok("one relevant memory becomes one context item", len(adapted.items) == 1)
item = adapted.items[0]
ok("memory source is canonical", item.source_type is ContextSourceType.OWNER_MEMORY)
ok("owner evidence maps to owner-direct trust", item.trust_class is TrustClass.OWNER_DIRECT)
ok("explicit high-confidence memory is known", item.certainty is Certainty.KNOWN)
ok("memory never gains instruction authority", item.instruction_authority is False)
ok("provenance is retained", item.provenance_ref == "conversation:42")
ok("owner chip remains available", adapted.chips[0]["memory_id"] == 1)
ok("prompt states memory grants no permission", "grants no permissions" in adapted.prompt_block)

filtered = owner_intelligence.adapt_retrieval([
    memory(2, sensitive=True),
    memory(3, redacted=True),
    memory(4, status="pending"),
    memory(5, signals={"recency": 0.0}),
    memory(6, certainty="contradicted"),
], mode="chat")
ok("sensitive stale contradicted and inactive memory are excluded", filtered.items == ())

hedged = owner_intelligence.adapt_retrieval([
    memory(7, hedged=True, explicitness="inferred", trust="untrusted"),
], mode="agent")
ok("inferred memory stays visibly uncertain", hedged.items[0].certainty is Certainty.INFERRED)
ok("imported memory stays untrusted", hedged.items[0].trust_class is TrustClass.UNTRUSTED_CONTENT)
ok("uncertain prompt text is hedged", "(unconfirmed)" in hedged.prompt_block)

source = inspect.getsource(owner_intelligence)
ok("adapter does not import Conductor", "core.conductor" not in source)
ok("adapter does not duplicate Brain persistence", "brain_memory_v2" not in source)
from core import context_manager  # noqa: E402
ok("Context Manager uses the typed adapter", "owner_intelligence" in inspect.getsource(context_manager.build_manifest))

print(f"\n{len(FAILURES)} failures")
raise SystemExit(1 if FAILURES else 0)
