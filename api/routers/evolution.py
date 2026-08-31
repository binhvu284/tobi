"""Evolution / Tier progression API — /api/evolution, /api/awakening, /api/evolution/reflect.

Extracted from api/dashboard.py (refactor Slice — pre-#21 decomposition). Byte-
identical: the _load_evo_snapshot/_save_evo_snapshot/_build_evo_response/
_build_reflection helpers + 3 routes; only @app.* -> @router.*. Awakening detection
comes from core.awakening_detect; version from core.release_manager. Free-var set
verified by isolated-pyflakes analysis. See docs/REFACTORING_PLAN.md.
"""
from __future__ import annotations

import sqlite3  # noqa: F401 - used in type hints
from datetime import datetime, timezone  # noqa: F401 - used by some handlers

from fastapi import APIRouter

from api.deps import _count, _get_conn
from core import agent_tier
from core.awakening_detect import _AGENT_EVIDENCE_TIER_ID, _TIER_DEFINITIONS, _detect_abilities
from core.release_manager import current_developer_version

router = APIRouter(tags=["evolution"])


# ── Evolution / Tier progression system ─────────────────────────────────────

def _load_evo_snapshot(conn: sqlite3.Connection) -> dict[str, str]:
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS evolution_snapshots (
                ability_id TEXT PRIMARY KEY,
                status TEXT NOT NULL DEFAULT 'inactive',
                detected_at TEXT,
                first_activated_at TEXT
            )
        """)
        conn.commit()
        rows = conn.execute("SELECT ability_id, status FROM evolution_snapshots").fetchall()
        return {r[0]: r[1] for r in rows}
    except Exception:
        return {}


def _save_evo_snapshot(conn: sqlite3.Connection, statuses: dict) -> None:
    now = datetime.now(timezone.utc).isoformat()
    for ability_id, val in statuses.items():
        # values are bool (legacy detector) or a 4-valued string (Awakening registry #17)
        status = val if isinstance(val, str) else ("active" if val else "inactive")
        conn.execute("""
            INSERT INTO evolution_snapshots (ability_id, status, detected_at, first_activated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(ability_id) DO UPDATE SET
                status = excluded.status,
                detected_at = excluded.detected_at,
                first_activated_at = CASE
                    WHEN evolution_snapshots.first_activated_at IS NULL AND excluded.status = 'active'
                        THEN excluded.detected_at
                    ELSE evolution_snapshots.first_activated_at
                END
        """, (ability_id, status, now, now))
    conn.commit()


def _build_evo_response(
    statuses: dict[str, bool],
    prev: dict[str, str],
    conn=None,
    current_release: str | None = None,
):
    just_unlocked: list[int] = []
    tiers_out = []

    # Tier 1 (Awakening) is sourced from the evidence-based registry (#17), not the static
    # bool detector — its 9 abilities carry a 4-valued status (active|partial|setup_needed|
    # inactive) + evidence/missing/setup_actions, and only 'active' counts toward progress.
    awakening_pillars = None
    awakening_labels = None
    agent_pillars = agent_tier.unavailable_pillars("Agent evidence registry is unavailable.")
    agent_labels = agent_tier.pillar_labels()
    if conn is not None:
        try:
            from core import awakening as _awk
            awakening_pillars = _awk.tier1_pillars(conn)
            awakening_labels = _awk.pillar_labels()
        except Exception:
            awakening_pillars = None
        try:
            agent_pillars = agent_tier.tier2_pillars(
                conn, current_release=current_release or current_developer_version(conn)
            )
        except Exception:
            pass

    for tier in _TIER_DEFINITIONS:
        use_awakening = tier["id"] == 1 and awakening_pillars is not None
        use_agent = tier["id"] == _AGENT_EVIDENCE_TIER_ID
        if use_awakening:
            pillars_src = awakening_pillars
        elif use_agent:
            pillars_src = agent_pillars
        else:
            pillars_src = tier["pillars"]

        all_ids: list[str] = []
        active_count = 0
        pillars_out: dict = {}

        for pillar_key, abilities in pillars_src.items():
            out = []
            for ab in abilities:
                ab_id = ab["id"]
                if "status" in ab:  # Awakening ability: 4-valued status already resolved
                    status = ab["status"]
                    is_active = status == "active"
                else:
                    is_active = statuses.get(ab_id, False)
                    status = "active" if is_active else "inactive"
                was_active = prev.get(ab_id) == "active"
                all_ids.append(ab_id)
                if is_active:
                    active_count += 1
                out.append({**ab, "status": status,
                             "just_activated": is_active and not was_active})
            pillars_out[pillar_key] = out

        total = len(all_ids)
        complete = active_count == total and total > 0
        was_complete = all(prev.get(aid) == "active" for aid in all_ids)
        if complete and not was_complete:
            just_unlocked.append(tier["id"])

        tier_obj = {
            **{k: v for k, v in tier.items() if k != "pillars"},
            "pillars": pillars_out,
            "active_count": active_count,
            "total_count": total,
            "progress_pct": round(active_count / total * 100) if total else 0,
            "complete": complete,
        }
        if use_awakening and awakening_labels:
            tier_obj["pillar_labels"] = awakening_labels
        elif use_agent:
            tier_obj["pillar_labels"] = agent_labels
        tiers_out.append(tier_obj)

    return tiers_out, just_unlocked


@router.get("/api/evolution")
async def get_evolution():
    conn = _get_conn()
    statuses = _detect_abilities(conn)
    prev = _load_evo_snapshot(conn)
    app_version = current_developer_version(conn)
    tiers, just_unlocked = _build_evo_response(
        statuses, prev, conn, current_release=app_version
    )
    # persist the Awakening 4-valued statuses too so just-activated survives reloads (#17)
    try:
        from core import awakening as _awk
        awk_status = _awk.status_map(conn)
    except Exception:
        awk_status = {}
    agent_status = {
        ability["id"]: ability["status"]
        for tier in tiers if tier["id"] == 2
        for pillar in tier["pillars"].values()
        for ability in pillar
    }
    _save_evo_snapshot(conn, {**statuses, **awk_status, **agent_status})
    conn.close()

    total_abilities = sum(t["total_count"] for t in tiers)
    total_active = sum(t["active_count"] for t in tiers)
    jarvis_pct = round(total_active / total_abilities * 100) if total_abilities else 0

    current_tier = next((t["id"] for t in tiers if not t["complete"]), tiers[-1]["id"])
    current_tier_data = next(tier for tier in tiers if tier["id"] == current_tier)
    missing = [
        ab for pillar in current_tier_data["pillars"].values()
        for ab in pillar if ab["status"] != "active"
    ]

    return {
        "tiers": tiers,
        "version": app_version,
        "current_tier": current_tier,
        "jarvis_pct": jarvis_pct,
        "total_active": total_active,
        "total_abilities": total_abilities,
        "just_unlocked": just_unlocked,
        "missing_in_current_tier": missing,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/api/awakening")
async def get_awakening():
    """Tier 1 (Awakening) evidence report (#17) — the single source read by the Evolution
    guided panel, the Ability page mirror, and TOBI's awakening_status tool."""
    from core import awakening
    conn = _get_conn()
    try:
        abilities = awakening.evaluate(conn)
        summary = awakening.summary(conn)
    finally:
        conn.close()
    return {
        "tier": 1,
        "tier_name": "Awakening",
        "categories": [
            {"key": "persistent_memory", "label": "Persistent Memory"},
            {"key": "identity_personality", "label": "Identity & Personality"},
            {"key": "basic_real_world_action", "label": "Basic Real-World Action"},
        ],
        "abilities": abilities,
        "active_count": summary["active_count"],
        "total": summary["total"],
        "progress_pct": summary["progress_pct"],
        "complete": summary["complete"],
        "sensitive_pending_review": summary["sensitive_pending_review"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _build_reflection(conn: sqlite3.Connection) -> tuple[str, dict[str, int]]:
    """Compose a genuine self-reflection from real activity. Uses the connected
    LLM when available; falls back to a deterministic summary so the lessons
    store can be seeded even with no model key. Returns (text, stats)."""
    stats = {
        "conversations": _count(conn, "SELECT COUNT(*) FROM conversations"),
        "projects":      _count(conn, "SELECT COUNT(*) FROM projects"),
        "tasks":         _count(conn, "SELECT COUNT(*) FROM tasks"),
        "lessons":       _count(conn, "SELECT COUNT(*) FROM lessons"),
        "reports":       _count(conn, "SELECT COUNT(*) FROM reports"),
        "missions":      _count(conn, "SELECT COUNT(*) FROM missions"),
        "agents":        _count(conn, "SELECT COUNT(*) FROM agents"),
    }
    recent_lessons = [
        f"- [{r[0]}] {r[1] or ''}: {(r[2] or '')[:120]}"
        for r in conn.execute(
            "SELECT lesson_type, title, content FROM lessons ORDER BY created_at DESC LIMIT 8"
        ).fetchall()
    ]
    lessons_text = "\n".join(recent_lessons) if recent_lessons else "No lessons yet — this is the first."

    deterministic = (
        "First self-reflection — institutional memory begins.\n"
        f"- State: {stats['conversations']} conversations, {stats['projects']} projects, "
        f"{stats['tasks']} tasks, {stats['missions']} missions, {stats['agents']} agents on record.\n"
        f"- Genesis (Tier 0) is essentially complete: persona, memory, classifier, coding agent, "
        f"integrations and always-on presence are live.\n"
        "- What went well: the foundation is wired end-to-end and the secrets vault now lets new "
        "abilities light up without a restart.\n"
        "- To improve next: turn repeated lessons into reusable skills, and let reflection run "
        "automatically after each cycle rather than only weekly.\n"
        "- Insight: a Jarvis is built one logged lesson at a time — this entry is lesson #1."
    )

    try:
        from core.model_router import llm_complete
        prompt = (
            "You are Tobi, a personal AI agent writing your very first self-reflection lesson — "
            "the seed of your institutional memory.\n\n"
            f"Activity so far: {stats['conversations']} conversations, {stats['projects']} projects, "
            f"{stats['tasks']} tasks, {stats['missions']} missions, {stats['agents']} agents, "
            f"{stats['reports']} reports.\n"
            f"Recent lessons:\n{lessons_text}\n\n"
            "Write a concise, honest reflection (4-6 short bullet points): what is working, what to "
            "improve, and one insight to carry forward. Be specific and grounded in the numbers above. "
            "Under 180 words. No preamble."
        )
        text = (llm_complete(prompt, task_type="simple", max_tokens=400) or "").strip()
        if len(text) < 40:  # model returned nothing useful → fall back
            text = deterministic
    except Exception:
        text = deterministic

    return text, stats


@router.post("/api/evolution/reflect")
async def post_evolution_reflect():
    """On-demand self-reflection. Writes a genuine lesson to the self-reflection
    DB, which activates the Genesis `lessons_store` ability (it keys off the
    lessons table having rows, mirroring how conversation_history keys off
    conversations). The weekly job does the same on Sundays — this lets the
    owner seed/refresh it any time."""
    conn = _get_conn()
    try:
        text, stats = _build_reflection(conn)
    finally:
        conn.close()

    from core.database import add_lesson
    title = f"Self-reflection {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    add_lesson(content=text, title=title, lesson_type="insight", impact_score=6)

    # Re-detect so the caller learns whether the ability flipped on.
    conn = _get_conn()
    statuses = _detect_abilities(conn)
    conn.close()

    return {
        "ok": True,
        "lesson": {"title": title, "content": text, "lesson_type": "insight"},
        "lessons_store_active": statuses.get("lessons_store", False),
        "stats": stats,
    }
