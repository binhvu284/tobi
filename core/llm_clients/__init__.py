"""LLM provider clients (pre-#21 refactor — Phase 4).

The provider client classes were extracted out of ``core/model_router.py`` (1,040
LOC) into one module per backend, so the router keeps only routing/config concerns:

  - ``base``          — ``BaseLLMClient`` + the shared usage-attribution context,
                        ``DEFAULT_TIMEOUT_S`` and the ``_norm_finish``/``_usage_dict``/
                        ``estimate_tokens`` helpers every client uses.
  - ``openrouter``    — ``OpenRouterClient``
  - ``claude``        — ``ClaudeClient`` (native Anthropic, thinking-block safe)
  - ``openai_compat`` — ``OpenAICompatibleClient``
  - ``codex``         — ``CodexClient``
  - ``fallback``      — ``FallbackClient`` (ordered chain)

Behavior-preserving move: ``core/model_router.py`` imports every one of these back
into its namespace, so existing call sites (``from core.model_router import
ClaudeClient``, ``model_router.FallbackClient``, …) keep working unchanged.
See ``docs/REFACTORING_PLAN.md``.
"""
