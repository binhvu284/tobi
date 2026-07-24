"""Conductor tool implementations (pre-#21 refactor — Phase 2).

The ~60 ``tool_*`` functions the Conductor exposes were extracted out of
``core/conductor.py`` (which had grown to 3,121 LOC) into this package, one
cohesive group per module, plus ``common.py`` for the helpers/constants shared
across tools. This is a **behavior-preserving move**: ``core/conductor.py`` keeps
the orchestration loop (``answer``), the tool-registry assembly
(``READ_TOOLS``/``OPTIONAL_TOOLS``/``ACT_TOOLS``/``ALL_TOOLS``/``RISK``/``TOOL_SPECS``),
the action audit/confirm path, and the persona/prompt builders, and imports the
tool functions from here to populate the registry.

The dependency is one-directional (tool modules → ``common``; ``conductor`` →
tool modules), so there is no import cycle. See ``docs/REFACTORING_PLAN.md``.
"""
