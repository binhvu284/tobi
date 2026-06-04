"""
THE OFFICE — multi-agent mission engine (Mission Control Module 2, spec §4).

First cut = happy-path linear orchestration: a mission runs its pinned workflow
steps in order (e.g. Sunday → Alphabet → Friday), Tobi-mediated (each step gets
the accumulated prior outputs as context; sub-agents never call each other —
hub-and-spoke, D31/D68). Each step records a `mission_steps` row + an
`llm_usage` row; Tobi writes a close-out summary (D69).

Provider binding (D26/D36) reuses `core.model_router.BaseLLMClient`. A
`MockLLMClient` makes the whole engine verifiable with **zero** network / keys /
cost (canned text + synthetic token counts) — and is also the only way to get
non-zero token numbers for the D34 cost ledger (real free models cost $0).

Explicitly NOT in this first cut (documented follow-ons): validation gates
(D32), retry/escalate/circuit-breaker (D33), parallel missions + concurrency
caps (D56), prioritization scheduling (D57), mid-mission inject (D58), real
outward Telegram close-out send (D69 — recorded here, send is a follow-on).
"""
import os
import json
from typing import Any

from core.database import get_connection
from core.model_router import BaseLLMClient, OpenRouterClient, ClaudeClient


class MockLLMClient(BaseLLMClient):
    """Deterministic, offline stand-in. Records synthetic token usage."""

    def __init__(self, label: str = "agent"):
        self.label = label
        self.last_usage: dict[str, int] | None = None

    def complete(self, messages: list, system: str = None, max_tokens: int = 2000) -> str:
        user = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
        out = f"[{self.label}] (mock) completed step on: {user[:140].strip()}"
        pt = (len(system or "") + sum(len(m.get("content", "")) for m in messages)) // 4
        ct = max(1, len(out) // 4)
        self.last_usage = {"prompt_tokens": pt, "completion_tokens": ct, "total_tokens": pt + ct}
        return out


def make_client(agent: dict, force_mock: bool = False) -> tuple[BaseLLMClient, bool]:
    """Return (client, used_mock). Falls back to mock when forced, when the
    provider has no real client, or when the agent's key_ref env var is absent —
    so a mission always runs and never half-fails on a missing key."""
    provider = (agent.get("provider") or "").lower()
    key_ref = agent.get("key_ref")
    has_key = bool(key_ref and os.getenv(key_ref))
    label = agent.get("name") or agent.get("id") or "agent"
    if force_mock or provider == "mock" or not has_key or provider not in ("openrouter", "anthropic"):
        return MockLLMClient(label), True
    try:
        if provider == "openrouter":
            return OpenRouterClient(model=agent.get("model")), False
        if provider == "anthropic":
            return ClaudeClient(agent.get("model") or "claude-opus-4-20250514"), False
    except Exception:
        pass
    return MockLLMClient(label), True


def _estimate_usage(system: str, messages: list, out: str) -> dict[str, int]:
    pt = (len(system or "") + sum(len(m.get("content", "")) for m in messages)) // 4
    ct = max(1, len(out) // 4)
    return {"prompt_tokens": pt, "completion_tokens": ct, "total_tokens": pt + ct}


def _closeout(mission: dict, outputs: list[tuple], total_tokens: int) -> str:
    """Tobi's hub close-out summary (D69): goal, per-agent work, cost."""
    lines = [
        f"Mission '{mission['title']}' complete.",
        f"Goal: {mission.get('goal') or mission['title']}",
        "",
        "Work by agent:",
    ]
    for name, action, out in outputs:
        snippet = (out or "").strip().replace("\n", " ")
        lines.append(f"  • {name} — {action}: {snippet[:160]}")
    lines += ["", f"Total tokens: {total_tokens} across {len(outputs)} steps."]
    return "\n".join(lines)


def run_mission(mission_id: int, force_mock: bool = False, notify: bool = False) -> dict[str, Any]:
    """Execute a mission's pinned workflow, linearly, hub-and-spoke. Idempotent
    re-run: clears prior steps/usage for this mission first. `notify` is the
    outward Telegram send (D69) — OFF by default; the summary is always recorded."""
    conn = get_connection()
    m = conn.execute("SELECT * FROM missions WHERE id=?", (mission_id,)).fetchone()
    if m is None:
        conn.close()
        raise ValueError(f"unknown mission {mission_id}")
    m = dict(m)

    wf = conn.execute("SELECT * FROM workflows WHERE id=?", (m["workflow_id"],)).fetchone()
    steps_def = json.loads(wf["definition_json"]) if wf and wf["definition_json"] else []
    if not steps_def:
        conn.close()
        raise ValueError("mission has no workflow steps")

    # fresh run
    conn.execute("DELETE FROM mission_steps WHERE mission_id=?", (mission_id,))
    conn.execute("DELETE FROM llm_usage WHERE mission_id=?", (mission_id,))
    conn.execute(
        "UPDATE missions SET status='running', started_at=CURRENT_TIMESTAMP, summary=NULL, cost_tokens=0 WHERE id=?",
        (mission_id,),
    )
    conn.commit()

    context = m.get("goal") or m["title"]
    outputs: list[tuple] = []
    total_tokens = 0

    for seq, sd in enumerate(steps_def, 1):
        arow = conn.execute("SELECT * FROM agents WHERE id=?", (sd["agent_id"],)).fetchone()
        agent = dict(arow) if arow else {"id": sd["agent_id"], "name": sd["agent_id"]}
        action = sd.get("action", "work")

        cur = conn.execute(
            """INSERT INTO mission_steps (mission_id, seq, agent_id, action, status, input, started_at)
               VALUES (?,?,?,?, 'running', ?, CURRENT_TIMESTAMP)""",
            (mission_id, seq, agent["id"], action, context),
        )
        step_id = cur.lastrowid
        conn.execute(
            "UPDATE agent_state SET runtime_status='working', current_mission_id=?, detail=?, last_active_at=CURRENT_TIMESTAMP WHERE agent_id=?",
            (mission_id, f"{action} · {m['title']}", agent["id"]),
        )
        conn.commit()

        client, _used_mock = make_client(agent, force_mock=force_mock)
        system = (f"You are {agent['name']}, the {agent.get('role', '')} agent in Tobi's office. "
                  f"Mission: {m['title']}. Perform the '{action}' step and hand the result back to Tobi.")
        messages = [{"role": "user", "content": f"Mission goal: {m.get('goal') or m['title']}\n\n"
                                                 f"Prior work (Tobi-mediated handoff):\n{context}"}]
        try:
            out = client.complete(messages, system=system, max_tokens=int(agent.get("max_tokens") or 2000))
        except Exception as e:  # noqa: BLE001 — fail the step, block the mission, free the agent
            conn.execute(
                "UPDATE mission_steps SET status='failed', output=?, completed_at=CURRENT_TIMESTAMP WHERE id=?",
                (f"(error: {str(e)[:200]})", step_id),
            )
            conn.execute("UPDATE missions SET status='blocked' WHERE id=?", (mission_id,))
            conn.execute(
                "UPDATE agent_state SET runtime_status='idle', current_mission_id=NULL, detail='idle' WHERE agent_id=?",
                (agent["id"],),
            )
            conn.commit()
            conn.close()
            return {"ok": False, "mission_id": mission_id, "failed_step": seq, "error": str(e)}

        usage = getattr(client, "last_usage", None) or _estimate_usage(system, messages, out)
        tokens = int(usage["total_tokens"])
        total_tokens += tokens

        conn.execute(
            "UPDATE mission_steps SET status='done', output=?, tokens=?, completed_at=CURRENT_TIMESTAMP WHERE id=?",
            (out, tokens, step_id),
        )
        conn.execute(
            """INSERT INTO llm_usage (agent_id, mission_id, provider, model, prompt_tokens, completion_tokens, total_tokens, cost)
               VALUES (?,?,?,?,?,?,?,0)""",
            (agent["id"], mission_id, agent.get("provider"), agent.get("model"),
             usage["prompt_tokens"], usage["completion_tokens"], tokens),
        )
        conn.execute(
            "UPDATE agent_state SET runtime_status='idle', current_mission_id=NULL, detail='idle' WHERE agent_id=?",
            (agent["id"],),
        )
        conn.commit()

        outputs.append((agent["name"], action, out))
        context = "\n".join(f"- {n} ({act}): {(o or '')[:300]}" for n, act, o in outputs)

    summary = _closeout(m, outputs, total_tokens)
    conn.execute(
        "UPDATE missions SET status='done', summary=?, cost_tokens=?, completed_at=CURRENT_TIMESTAMP WHERE id=?",
        (summary, total_tokens, mission_id),
    )
    conn.commit()
    conn.close()

    if notify:
        _notify_closeout(summary)  # outward-facing; off during verification (dry-run)

    return {"ok": True, "mission_id": mission_id, "steps": len(outputs),
            "tokens": total_tokens, "summary": summary}


def _notify_closeout(summary: str) -> None:
    """Outward Telegram close-out (D69). Follow-on: wire to the single Hermes
    gateway bot (H16). Intentionally a no-op here so verification never sends."""
    return None
