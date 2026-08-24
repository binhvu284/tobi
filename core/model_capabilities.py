"""
MODEL CAPABILITIES — TOBI Premium Ability (#14).

A small, **explicit** local registry of what each model can do (vision / reasoning /
context window). The chat + reader layers use it so they stop relying on fragile
substring guesses scattered across the codebase.

Ids are `provider:model` (e.g. ``anthropic:claude-opus-4-8``) but the same model
also shows up under other prefixes (``openrouter:anthropic/claude-opus-4-8``), so
rules are matched as a **substring** of the lowercased id — one rule covers every
prefix a model appears under. Rules are ordered **most-specific first**; the first
hit wins. Anything unmatched falls back to permissive fragment matching so an
obvious-but-unlisted model still resolves instead of failing closed.

``model_router.supports_vision()`` delegates here for backward compatibility.
"""
from __future__ import annotations

from typing import TypedDict


class Caps(TypedDict):
    vision: bool
    reasoning: bool
    context: int


# Ordered, most-specific first. Matched via `fragment in model_id.lower()`.
_RULES: list[tuple[str, Caps]] = [
    # ── Anthropic Claude (all modern Claude models are multimodal) ──
    ("claude-3-5-haiku", {"vision": True, "reasoning": False, "context": 200000}),
    ("claude-haiku-4", {"vision": True, "reasoning": False, "context": 200000}),
    ("claude-3-haiku", {"vision": True, "reasoning": False, "context": 200000}),
    ("claude-3-7", {"vision": True, "reasoning": True, "context": 200000}),
    ("claude-sonnet-4", {"vision": True, "reasoning": True, "context": 200000}),
    ("claude-opus-4", {"vision": True, "reasoning": True, "context": 200000}),
    ("claude", {"vision": True, "reasoning": False, "context": 200000}),
    # ── OpenAI ──
    ("gpt-4o-mini", {"vision": True, "reasoning": False, "context": 128000}),
    ("gpt-4o", {"vision": True, "reasoning": False, "context": 128000}),
    ("gpt-4.1", {"vision": True, "reasoning": False, "context": 1000000}),
    ("gpt-4-turbo", {"vision": True, "reasoning": False, "context": 128000}),
    ("gpt-4", {"vision": False, "reasoning": False, "context": 8192}),
    ("gpt-3.5", {"vision": False, "reasoning": False, "context": 16385}),
    ("gpt-5.6-sol", {"vision": True, "reasoning": True, "context": 200000}),
    ("gpt-5.6-terra", {"vision": True, "reasoning": True, "context": 200000}),
    ("gpt-5.6-luna", {"vision": True, "reasoning": True, "context": 200000}),
    ("gpt-5.6", {"vision": True, "reasoning": True, "context": 200000}),
    ("gpt-5.5", {"vision": True, "reasoning": True, "context": 200000}),
    ("gpt-5.4", {"vision": True, "reasoning": True, "context": 200000}),
    ("gpt-5.4-mini", {"vision": True, "reasoning": True, "context": 200000}),
    ("gpt-5-codex", {"vision": True, "reasoning": True, "context": 200000}),  # deprecated alias
    ("gpt-5", {"vision": True, "reasoning": True, "context": 200000}),
    ("o4-mini", {"vision": True, "reasoning": True, "context": 200000}),
    ("o3-mini", {"vision": False, "reasoning": True, "context": 200000}),
    ("o3", {"vision": True, "reasoning": True, "context": 200000}),
    ("o1-mini", {"vision": False, "reasoning": True, "context": 128000}),
    ("o1", {"vision": True, "reasoning": True, "context": 200000}),
    # ── Google Gemini ──
    ("gemini-2.5-flash", {"vision": True, "reasoning": True, "context": 1000000}),
    ("gemini-2.5-pro", {"vision": True, "reasoning": True, "context": 1000000}),
    ("gemini", {"vision": True, "reasoning": False, "context": 1000000}),
    # ── xAI Grok ──
    ("grok-4", {"vision": True, "reasoning": True, "context": 131072}),
    ("grok-vision", {"vision": True, "reasoning": False, "context": 131072}),
    ("grok-3-mini", {"vision": False, "reasoning": True, "context": 131072}),
    ("grok-3", {"vision": False, "reasoning": False, "context": 131072}),
    ("grok", {"vision": False, "reasoning": False, "context": 131072}),
    # ── GLM (Z.ai) — only the -v variants see images ──
    ("glm-4.5v", {"vision": True, "reasoning": False, "context": 131072}),
    ("glm-4.6", {"vision": False, "reasoning": True, "context": 200000}),
    ("glm", {"vision": False, "reasoning": False, "context": 131072}),
    # ── DeepSeek — V4 takes a 1M context and thinks; only -vision-exp sees images ──
    ("deepseek-v4-flash-vision", {"vision": True, "reasoning": True, "context": 1000000}),
    ("deepseek-v4-pro", {"vision": False, "reasoning": True, "context": 1000000}),
    ("deepseek-v4-flash", {"vision": False, "reasoning": True, "context": 1000000}),
    ("deepseek-r1", {"vision": False, "reasoning": True, "context": 131072}),
    ("deepseek", {"vision": False, "reasoning": False, "context": 131072}),
    # ── Open models (OpenRouter / Ollama) ──
    ("llava", {"vision": True, "reasoning": False, "context": 32768}),
    ("qwen2.5-vl", {"vision": True, "reasoning": False, "context": 131072}),
    ("qwen2-vl", {"vision": True, "reasoning": False, "context": 131072}),
    ("nemotron", {"vision": False, "reasoning": False, "context": 131072}),
]

# Backup only: obvious vision fragments for models not in the table above.
_VISION_FALLBACK = ("claude", "gpt-4o", "gpt-4.1", "gpt-5", "o1", "o3", "o4",
                    "gemini", "grok-4", "grok-vision", "llava", "-vl")

# Backup only: coarse context sizing for unmatched models.
_CONTEXT_FALLBACK = [("claude", 200000), ("gemini", 1000000), ("gpt-4o", 128000),
                     ("gpt-5", 200000), ("o3", 200000), ("grok", 131072),
                     ("glm", 131072), ("llama", 131072), ("qwen", 32768)]

_DEFAULT: Caps = {"vision": False, "reasoning": False, "context": 128000}


def _fallback(name: str) -> Caps:
    ctx = next((lim for frag, lim in _CONTEXT_FALLBACK if frag in name), _DEFAULT["context"])
    return {"vision": any(f in name for f in _VISION_FALLBACK), "reasoning": False, "context": ctx}


def capabilities_for(model_id: str) -> Caps:
    """Best-known capabilities for a 'provider:model' id (never raises)."""
    name = (model_id or "").lower()
    if not name:
        return dict(_DEFAULT)  # type: ignore[return-value]
    for frag, caps in _RULES:
        if frag in name:
            return dict(caps)  # type: ignore[return-value]
    return _fallback(name)


def supports_vision(model_id: str) -> bool:
    return bool(capabilities_for(model_id)["vision"])


def supports_reasoning(model_id: str) -> bool:
    return bool(capabilities_for(model_id)["reasoning"])


def context_window(model_id: str) -> int:
    return int(capabilities_for(model_id)["context"])
