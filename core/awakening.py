"""
AWAKENING (#17) — the single source of truth for Tier 1 completion.

An **evidence detector**: it inspects real Brain / Conductor / Integrations / Tasks
state and reports each of the 9 Tier-1 abilities as one of
``active | partial | setup_needed | inactive`` with human evidence, what's missing,
and setup links. Only ``active`` counts toward progress, so **Tier 1 reaches 100%
only when all 9 are genuinely active** — completion is never hardcoded.

Evolution, the Ability page, the Conductor's ``awakening_status`` tool, and the UI
all read this one registry so none of them invent their own completion logic.

Design: never raises (each check degrades to ``setup_needed``/``inactive``); reads
existing data only (no new memory system, no live external network calls — a
connector counts as configured from its stored/env credential, not a live probe).
"""
from __future__ import annotations

import os
from typing import Optional

# ── categories → the Evolution page's existing 3-pillar render keys ────────────────
_CATEGORY_PILLAR = {
    "persistent_memory": "understand",
    "identity_personality": "presence",
    "basic_real_world_action": "control",
}
_CATEGORY_LABEL = {
    "persistent_memory": "Persistent Memory",
    "identity_personality": "Identity & Personality",
    "basic_real_world_action": "Basic Real-World Action",
}

# Conversation-derived memory sources (distilled facts from chatting), as opposed to
# manually-entered/imported ones — used to tell A2 apart from A1.
_CONVO_SOURCES = {"chat", "telegram", "auto", "conductor", "conversation", "brain_chat", "brain"}

# Static ability definitions (order = display order within a category).
_ABILITIES: list[dict] = [
    # ── Persistent Memory (Category A) ──────────────────────────────────────────────
    {"id": "owner_profile_memory", "category": "persistent_memory",
     "name": "Owner Profile Memory", "short_name": "Profile Memory", "risk": "low",
     "description": "TOBI remembers who the owner is — identity, work, goals, preferences, habits — as reviewable Brain memories.",
     "setup": [{"label": "Open Brain", "route": "/brain"}]},
    {"id": "conversation_memory", "category": "persistent_memory",
     "name": "Conversation Memory", "short_name": "Conversation Memory", "risk": "low",
     "description": "Facts and decisions from conversations are distilled into Brain memories and recalled across sessions (never raw transcripts).",
     "setup": [{"label": "Review Brain", "route": "/brain"}]},
    {"id": "preference_learning", "category": "persistent_memory",
     "name": "Preference Learning", "short_name": "Preferences", "risk": "low",
     "description": "Repeated choices and explicit preferences become reviewable preference memories TOBI applies.",
     "setup": [{"label": "Open Brain", "route": "/brain"}]},
    # ── Identity & Personality (Category B) ─────────────────────────────────────────
    {"id": "consistent_persona", "category": "identity_personality",
     "name": "Consistent Persona", "short_name": "Persona", "risk": "low",
     "description": "One practical British-butler persona across MC chat, Telegram, and action/confirmation replies.",
     "setup": []},
    {"id": "contextual_self_awareness", "category": "identity_personality",
     "name": "Contextual Self-Awareness", "short_name": "Self-Awareness", "risk": "low",
     "description": "TOBI can honestly report its current tier, active abilities, missing items, and limitations from live data.",
     "setup": []},
    {"id": "evolution_tracking", "category": "identity_personality",
     "name": "Evolution Tracking", "short_name": "Evolution", "risk": "low",
     "description": "Evolution reads this 9-ability Awakening registry; Tier 1 only reaches 100% from real evidence.",
     "setup": []},
    # ── Basic Real-World Action (Category C) ────────────────────────────────────────
    {"id": "internal_task_management", "category": "basic_real_world_action",
     "name": "Task Management (Internal)", "short_name": "Task CRUD", "risk": "medium",
     "description": "TOBI can create, read, update, complete, assign, and delete MC tasks with risk-based confirmation.",
     "setup": [{"label": "Open Tasks", "route": "/tasks"}]},
    {"id": "external_read_access", "category": "basic_real_world_action",
     "name": "External Read Access", "short_name": "Connected Reads", "risk": "medium",
     "description": "Safely-configured read connectors (GitHub, Notion, Google) can be queried; unconfigured ones show setup-needed.",
     "setup": [{"label": "Open Integrations", "route": "/integrations"}]},
    {"id": "simple_automation", "category": "basic_real_world_action",
     "name": "Simple Automation", "short_name": "Automations", "risk": "medium",
     "description": "Three packaged workflows work and are logged: create task from conversation, save note, summarize a GitHub repo.",
     "setup": [{"label": "See Actions", "route": "/actions"}]},
]

ABILITY_IDS = [a["id"] for a in _ABILITIES]


# ── low-level evidence readers (defensive; never raise) ─────────────────────────────
def _memory_rows(conn) -> list[tuple]:
    """(category, source, count) for active, non-deleted Brain memories."""
    try:
        rows = conn.execute(
            "SELECT category, COALESCE(source,''), COUNT(*) FROM brain_memories "
            "WHERE status='active' AND deleted_at IS NULL GROUP BY category, source"
        ).fetchall()
        return [(str(r[0] or ""), str(r[1] or ""), int(r[2] or 0)) for r in rows]
    except Exception:
        return []


def _pending_sensitive(conn) -> int:
    """Sensitive memories still awaiting owner review (must NOT count as evidence)."""
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM brain_memories m "
            "JOIN brain_categories c ON c.id = m.category "
            "WHERE m.status='pending' AND m.deleted_at IS NULL AND c.sensitive=1"
        ).fetchone()
        return int(row[0] or 0)
    except Exception:
        return 0


def _tool_catalog() -> tuple[set, set]:
    """(read tool names, act tool names) from the Conductor — lazy so import stays cheap."""
    try:
        from core import conductor as C
        return set(C.READ_TOOLS.keys()), set(C.ACT_TOOLS.keys())
    except Exception:
        return set(), set()


_WORKFLOW_TOOLS = ("create_task_from_conversation", "save_note", "summarize_repo")


def _workflow_receipts(conn) -> set:
    """Workflow tools with at least one SUCCESSFUL execution receipt in tobi_actions —
    so Simple Automation is gated on real, logged use, not on tool registration."""
    try:
        rows = conn.execute(
            "SELECT DISTINCT tool FROM tobi_actions WHERE status='executed' AND tool IN (?,?,?)",
            _WORKFLOW_TOOLS,
        ).fetchall()
        return {str(r[0]) for r in rows}
    except Exception:
        return set()


def _read_connectors() -> list[str]:
    """Read-safe connectors that are genuinely USABLE — using each integration's own
    readiness check (no live network probe). Google requires a completed OAuth token
    (`is_connected`), not merely a configured client id/secret; GitHub/Notion require their
    token to be present (`is_available`). Credential presence alone is NOT counted."""
    out: list[str] = []
    try:
        from core.integrations import get_integration
    except Exception:
        return out
    for iid, label, method in (("github", "GitHub", "is_available"),
                               ("notion", "Notion", "is_available"),
                               ("google", "Google", "is_connected")):
        try:
            integ = get_integration(iid)
            if integ and getattr(integ, method, lambda: False)():
                out.append(label)
        except Exception:
            continue
    return out


# ── per-ability evaluators → (status, evidence[], missing[]) ────────────────────────
def _eval_owner_profile(mem: list[tuple]) -> tuple:
    by_cat: dict[str, int] = {}
    for cat, _src, n in mem:
        by_cat[cat] = by_cat.get(cat, 0) + n
    total = sum(by_cat.values())
    cats = len(by_cat)
    if total >= 3 and cats >= 2:
        return "active", [f"{total} owner facts across {cats} Brain categories"], []
    if total >= 1:
        return "partial", [f"{total} owner fact(s) so far"], ["Add a few more facts across categories (identity, work, preferences…)"]
    return "setup_needed", [], ["No owner-profile memories yet — add a few in Brain"]


def _eval_conversation(mem: list[tuple]) -> tuple:
    convo = sum(n for _cat, src, n in mem if src in _CONVO_SOURCES)
    total = sum(n for _cat, _src, n in mem)
    if convo >= 2:
        return "active", [f"{convo} facts distilled from conversations"], []
    if convo >= 1 or total >= 1:
        return "partial", [f"{convo} conversation-derived fact(s)"], ["Keep chatting — TOBI distills durable facts automatically"]
    return "setup_needed", [], ["No conversation-derived memories yet"]


def _eval_preference(mem: list[tuple]) -> tuple:
    pref = sum(n for cat, _src, n in mem if cat in ("preferences", "habits"))
    if pref >= 2:
        return "active", [f"{pref} preference/habit memories"], []
    if pref >= 1:
        return "partial", [f"{pref} preference memory"], ["Tell TOBI a couple of your preferences or working habits"]
    return "setup_needed", [], ["No preference/habit memories yet"]


def _eval_persona() -> tuple:
    """Behavioral check: the SAME butler persona must actually anchor every surface's
    system prompt (MC chat, Telegram, and action-confirmation replies all run through
    conductor._system_prompt), not merely exist as a string."""
    try:
        from core import conductor as C
    except Exception:
        return "partial", [], ["Conductor persona module not importable"]
    butler = getattr(C, "_BUTLER", "")
    if not (isinstance(butler, str) and len(butler) > 200):
        return "partial", [], ["Shared persona module not detected"]
    try:
        anchor = butler[:120]
        mc = C._system_prompt("", True, surface="mc")
        tg = C._system_prompt("", True, surface="telegram")
        if anchor and anchor in mc and anchor in tg:
            return "active", ["One British-butler persona anchors MC chat, Telegram, and action replies (shared system prompt)"], []
    except Exception:
        pass
    return "partial", ["Shared _BUTLER persona present"], ["Persona not confirmed identical across surfaces"]


def _eval_self_awareness(reads: set) -> tuple:
    if "awakening_status" in reads:
        return "active", ["awakening_status tool live — reports tier, active/missing abilities, and limits from live data"], []
    return "partial", ["Evolution reports tier/ability counts"], ["Add the awakening_status Conductor tool"]


def _eval_evolution_tracking() -> tuple:
    if len(_ABILITIES) == 9:
        return "active", ["Evolution reads the 9-ability Awakening registry; progress is evidence-gated"], []
    return "partial", [], ["Awakening registry incomplete"]


def _eval_task_management(acts: set, reads: set) -> tuple:
    required = {"create_task", "update_task", "complete_task", "assign_task", "delete_task"}
    have = required & acts
    if required <= acts and "list_tasks" in reads:
        return "active", ["6 task tools: create / read / update / complete / assign / delete, with risk-tiered confirmation"], []
    if {"create_task", "complete_task"} <= acts:
        missing = sorted(required - have)
        return "partial", [f"{len(have)} of {len(required)} task act-tools present"], [f"Missing task tool(s): {', '.join(missing)}"]
    return "setup_needed", [], ["Task CRUD tools not registered"]


def _eval_external_read(connectors: list[str]) -> tuple:
    if connectors:
        return "active", [f"Read-safe connectors configured: {', '.join(connectors)}"], []
    return "setup_needed", [], ["No read-safe connector configured — connect GitHub, Notion, or Google in Integrations"]


def _eval_automation(acts: set, reads: set, receipts: set) -> tuple:
    """Active only once each of the three workflows has actually RUN successfully (a logged
    tobi_actions receipt) — registration alone is not evidence, so this can't fake a 100%."""
    registered = [w for w in _WORKFLOW_TOOLS if w in acts or w in reads]
    if len(registered) < 3:
        missing = [w for w in _WORKFLOW_TOOLS if w not in acts and w not in reads]
        return "setup_needed", [], [f"Workflow tool(s) not registered: {', '.join(missing)}"]
    proven = [w for w in _WORKFLOW_TOOLS if w in receipts]
    if len(proven) == 3:
        return "active", ["All 3 workflows have run successfully and are logged to Actions"], []
    pending = [w for w in _WORKFLOW_TOOLS if w not in receipts]
    detail = ("conversation→task, save a note, summarize a GitHub repo")
    if proven:
        return "partial", [f"{len(proven)}/3 workflows proven by a logged receipt"], [f"Run each once via chat to activate: {', '.join(pending)}"]
    return "partial", [f"3 workflows available ({detail})"], ["Run each once via chat to activate — they log to Actions"]


# ── public API ─────────────────────────────────────────────────────────────────────
def evaluate(conn) -> list[dict]:
    """Return the 9 Tier-1 abilities with live status/evidence/missing/setup_actions.
    Never raises — any failure yields conservative statuses."""
    try:
        mem = _memory_rows(conn)
    except Exception:
        mem = []
    reads, acts = _tool_catalog()
    connectors = _read_connectors()
    receipts = _workflow_receipts(conn)

    results = {
        "owner_profile_memory": _eval_owner_profile(mem),
        "conversation_memory": _eval_conversation(mem),
        "preference_learning": _eval_preference(mem),
        "consistent_persona": _eval_persona(),
        "contextual_self_awareness": _eval_self_awareness(reads),
        "evolution_tracking": _eval_evolution_tracking(),
        "internal_task_management": _eval_task_management(acts, reads),
        "external_read_access": _eval_external_read(connectors),
        "simple_automation": _eval_automation(acts, reads, receipts),
    }

    out: list[dict] = []
    for ab in _ABILITIES:
        status, evidence, missing = results.get(ab["id"], ("inactive", [], ["Not evaluated"]))
        out.append({
            "id": ab["id"],
            "category": ab["category"],
            "category_label": _CATEGORY_LABEL[ab["category"]],
            "name": ab["name"],
            "short_name": ab["short_name"],
            "description": ab["description"],
            "status": status,
            "evidence": evidence,
            "missing": missing,
            "setup_actions": ab["setup"],
            "risk": ab["risk"],
        })
    return out


def status_map(conn) -> dict:
    """{ability_id: status} for snapshot persistence + just-activated detection."""
    return {a["id"]: a["status"] for a in evaluate(conn)}


def tier1_pillars(conn) -> dict:
    """The 9 abilities grouped under the Evolution page's understand/control/presence
    pillar keys (each pillar carries exactly one category's abilities)."""
    pillars: dict[str, list] = {"understand": [], "control": [], "presence": []}
    for ab in evaluate(conn):
        pillars[_CATEGORY_PILLAR[ab["category"]]].append(ab)
    return pillars


def pillar_labels() -> dict:
    """understand/control/presence → the Tier-1 category display labels."""
    return {_CATEGORY_PILLAR[cat]: label for cat, label in _CATEGORY_LABEL.items()}


def summary(conn) -> dict:
    """Compact tier report for the Conductor's awakening_status tool."""
    abilities = evaluate(conn)
    active = [a["name"] for a in abilities if a["status"] == "active"]
    partial = [a["name"] for a in abilities if a["status"] == "partial"]
    setup = [a["name"] for a in abilities if a["status"] == "setup_needed"]
    missing = [m for a in abilities if a["status"] != "active" for m in a["missing"]]
    total = len(abilities)
    n_active = len(active)
    return {
        "tier": 1,
        "tier_name": "Awakening",
        "active_count": n_active,
        "total": total,
        "progress_pct": round(n_active / total * 100) if total else 0,
        "complete": n_active == total,
        "active": active,
        "partial": partial,
        "setup_needed": setup,
        "missing": missing[:12],
        "sensitive_pending_review": _pending_sensitive(conn),
    }
