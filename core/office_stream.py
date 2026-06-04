"""
THE OFFICE — streaming mission engine (Mission Control Phase 4, war-room backbone).

Refactors the synchronous `core.office.run_mission` into a background task that emits
events as it runs, so the UI can animate live. Single-process (uvicorn) → one
module-level singleton broker (pub/sub + replay ring + control flags + task registry)
is sufficient (single-owner, D66).

Events (per mission): mission_start · step_start · step_delta · step_done ·
blackboard_update · paused · error · mission_done. Mock runs emit simulated token
deltas (deterministic, zero cost) so the war-room animates without spending tokens.

Steering (D58/D32) is checked **between steps** — pause/inject/cancel land after the
current step returns (a cancel can't interrupt an in-flight LLM call).
"""
import asyncio
import json
import math
import time
from typing import Any

from core.database import get_connection
from core.office import make_client, _estimate_usage, _closeout


class _Broker:
    def __init__(self) -> None:
        self.subs: dict[int, set[asyncio.Queue]] = {}
        self.log: dict[int, list[dict]] = {}          # replay ring per mission
        self.flags: dict[int, dict] = {}              # control flags per mission
        self.tasks: set[asyncio.Task] = set()         # hold background runs alive
        self._seq: dict[int, int] = {}

    def _next(self, mid: int) -> int:
        self._seq[mid] = self._seq.get(mid, 0) + 1
        return self._seq[mid]

    def publish(self, mid: int, etype: str, data: dict) -> dict:
        ev = {"seq": self._next(mid), "type": etype, "data": data, "ts": time.time()}
        self.log.setdefault(mid, []).append(ev)
        self.log[mid] = self.log[mid][-300:]
        for q in list(self.subs.get(mid, ())):
            try: q.put_nowait(ev)
            except Exception: pass  # noqa: BLE001
        return ev

    def subscribe(self, mid: int) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self.subs.setdefault(mid, set()).add(q)
        return q

    def unsubscribe(self, mid: int, q: asyncio.Queue) -> None:
        self.subs.get(mid, set()).discard(q)

    def replay(self, mid: int, since: int) -> list[dict]:
        return [e for e in self.log.get(mid, []) if e["seq"] > since]

    def flag(self, mid: int) -> dict:
        return self.flags.setdefault(mid, {"paused": False, "cancel": False, "injects": []})

    def is_running(self, mid: int) -> bool:
        log = self.log.get(mid, [])
        return bool(log) and log[-1]["type"] not in ("mission_done", "error")


broker = _Broker()


def _chunks(s: str, n: int) -> list[str]:
    size = max(1, math.ceil(len(s) / n))
    return [s[i:i + size] for i in range(0, len(s), size)] or [""]


async def run_mission_streamed(mission_id: int, mock: bool = False) -> None:
    b = broker
    flag = b.flag(mission_id)
    conn = get_connection()
    row = conn.execute("SELECT * FROM missions WHERE id=?", (mission_id,)).fetchone()
    if row is None:
        conn.close(); b.publish(mission_id, "error", {"message": "unknown mission"}); return
    m = dict(row)
    wf = conn.execute("SELECT * FROM workflows WHERE id=?", (m["workflow_id"],)).fetchone()
    steps = json.loads(wf["definition_json"]) if wf and wf["definition_json"] else []

    conn.execute("DELETE FROM mission_steps WHERE mission_id=?", (mission_id,))
    conn.execute("DELETE FROM llm_usage WHERE mission_id=?", (mission_id,))
    conn.execute("UPDATE missions SET status='running', started_at=CURRENT_TIMESTAMP, summary=NULL, cost_tokens=0 WHERE id=?", (mission_id,))
    conn.commit()
    b.publish(mission_id, "mission_start", {"title": m["title"], "goal": m.get("goal"), "steps": len(steps)})

    context = m.get("goal") or m["title"]
    outputs: list[tuple] = []
    total = 0

    for seq, sd in enumerate(steps, 1):
        while flag["paused"] and not flag["cancel"]:
            b.publish(mission_id, "paused", {"seq": seq})
            await asyncio.sleep(0.4)
        if flag["cancel"]:
            conn.execute("UPDATE missions SET status='cancelled', completed_at=CURRENT_TIMESTAMP WHERE id=?", (mission_id,))
            conn.commit(); conn.close()
            b.publish(mission_id, "mission_done", {"status": "cancelled", "tokens": total, "summary": "Cancelled by owner."})
            return
        if flag["injects"]:
            inj = "; ".join(flag["injects"]); flag["injects"] = []
            context += f"\n[Owner guidance: {inj}]"
            b.publish(mission_id, "blackboard_update", {"context": context})

        arow = conn.execute("SELECT * FROM agents WHERE id=?", (sd["agent_id"],)).fetchone()
        agent = dict(arow) if arow else {"id": sd["agent_id"], "name": sd["agent_id"]}
        action = sd.get("action", "work")
        cur = conn.execute(
            "INSERT INTO mission_steps (mission_id, seq, agent_id, action, status, input, started_at) VALUES (?,?,?,?, 'running', ?, CURRENT_TIMESTAMP)",
            (mission_id, seq, agent["id"], action, context))
        step_id = cur.lastrowid
        conn.execute("UPDATE agent_state SET runtime_status='working', current_mission_id=?, detail=?, last_active_at=CURRENT_TIMESTAMP WHERE agent_id=?",
                     (mission_id, f"{action} · {m['title']}", agent["id"]))
        conn.commit()
        b.publish(mission_id, "step_start", {"seq": seq, "agent_id": agent["id"], "agent": agent.get("name"), "action": action})

        system = (f"You are {agent['name']}, the {agent.get('role', '')} agent in Tobi's office. "
                  f"Mission: {m['title']}. Perform the '{action}' step and hand the result back to Tobi.")
        messages = [{"role": "user", "content": f"Mission goal: {m.get('goal') or m['title']}\n\nPrior work (Tobi-mediated handoff):\n{context}"}]
        try:
            client, used_mock = make_client(agent, force_mock=mock)
            if used_mock:
                out = f"[{agent.get('name')}] completed '{action}' — synthesized from prior context: {context[:90].replace(chr(10), ' ').strip()}…"
                acc = ""
                for chunk in _chunks(out, 7):
                    if flag["cancel"]: break
                    acc += chunk
                    b.publish(mission_id, "step_delta", {"seq": seq, "text": chunk})
                    await asyncio.sleep(0.12)
                out = acc
                usage = _estimate_usage(system, messages, out)
            else:
                out = await asyncio.to_thread(client.complete, messages, system, int(agent.get("max_tokens") or 2000))
                usage = getattr(client, "last_usage", None) or _estimate_usage(system, messages, out)
                b.publish(mission_id, "step_delta", {"seq": seq, "text": out})
        except Exception as e:  # noqa: BLE001
            conn.execute("UPDATE mission_steps SET status='failed', output=?, completed_at=CURRENT_TIMESTAMP WHERE id=?", (f"(error: {str(e)[:160]})", step_id))
            conn.execute("UPDATE missions SET status='blocked' WHERE id=?", (mission_id,))
            conn.execute("UPDATE agent_state SET runtime_status='idle', current_mission_id=NULL, detail='idle' WHERE agent_id=?", (agent["id"],))
            conn.commit(); conn.close()
            b.publish(mission_id, "error", {"seq": seq, "message": str(e)[:160]})
            b.publish(mission_id, "mission_done", {"status": "blocked", "tokens": total})
            return

        tokens = int(usage["total_tokens"]); total += tokens
        conn.execute("UPDATE mission_steps SET status='done', output=?, tokens=?, completed_at=CURRENT_TIMESTAMP WHERE id=?", (out, tokens, step_id))
        conn.execute("INSERT INTO llm_usage (agent_id, mission_id, provider, model, prompt_tokens, completion_tokens, total_tokens, cost) VALUES (?,?,?,?,?,?,?,0)",
                     (agent["id"], mission_id, agent.get("provider"), agent.get("model"), usage["prompt_tokens"], usage["completion_tokens"], tokens))
        conn.execute("UPDATE agent_state SET runtime_status='idle', current_mission_id=NULL, detail='idle' WHERE agent_id=?", (agent["id"],))
        conn.commit()
        outputs.append((agent.get("name"), action, out))
        context = "\n".join(f"- {n} ({a}): {(o or '')[:300]}" for n, a, o in outputs)
        b.publish(mission_id, "step_done", {"seq": seq, "agent_id": agent["id"], "tokens": tokens, "total_tokens": total, "output": out})
        b.publish(mission_id, "blackboard_update", {"context": context})

    summary = _closeout(m, outputs, total)
    conn.execute("UPDATE missions SET status='done', summary=?, cost_tokens=?, completed_at=CURRENT_TIMESTAMP WHERE id=?", (summary, total, mission_id))
    conn.commit(); conn.close()
    b.publish(mission_id, "mission_done", {"status": "done", "tokens": total, "summary": summary})


def start_run(mission_id: int, mock: bool = False) -> None:
    """Kick off a streamed run as a held background task (survives the POST)."""
    broker.flags[mission_id] = {"paused": False, "cancel": False, "injects": []}
    broker.log[mission_id] = []
    broker._seq[mission_id] = 0
    t = asyncio.create_task(run_mission_streamed(mission_id, mock))
    broker.tasks.add(t)
    t.add_done_callback(broker.tasks.discard)
