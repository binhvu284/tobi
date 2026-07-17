"""
Brain Memory V2 feedback + influence + action reflection (queue #20, T08).

Plain python, no pytest, isolated temp DB:
    python tests/test_brain_feedback.py
"""
import os
import sys
import tempfile

os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="tobi_bfb_"), "agent.db")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from core.database import init_database, get_connection  # noqa: E402
from core import vault, owner_flags  # noqa: E402
from core import brain_repository as repo  # noqa: E402
from core import brain_feedback as fb  # noqa: E402
from core import brain_retrieval as ret  # noqa: E402
from core.brain_contracts import (  # noqa: E402
    MemoryCandidate, MemoryType, Explicitness, MemoryStatus,
)

init_database()
conn = get_connection()
vault.setup(conn, "master-pass-123456", import_env=False)

PASS = 0


def ok(name: str, cond: bool, detail: str = ""):
    global PASS
    if not cond:
        print(f"❌ {name} {detail}")
        sys.exit(1)
    PASS += 1
    print(f"✅ {name}")


def raises(fn, exc=Exception) -> bool:
    try:
        fn()
    except exc:
        return True
    except Exception:
        return False
    return False


def count(sql, args=()):
    return conn.execute(sql, args).fetchone()[0]


def seed(text, **kw):
    base = dict(distilled_text=text, memory_type=MemoryType.FACT,
                explicitness=Explicitness.EXPLICIT, confidence=0.9,
                durability=1, actionability=1, specificity=1, source_strength=1,
                evidence_excerpt=f"evidence for: {text[:60]}", source_ref="chat:seed")
    base.update(kw)
    return repo.save(MemoryCandidate(**base), status=MemoryStatus.ACTIVE, conn=conn)


# two near-equal memories on the same topic — feedback should split their ranking
m_good = seed("Owner plans sprints around the delivery queue cadence")
m_bad = seed("Owner plans sprints around the delivery queue tempo")

# ── feedback: validation + signal math ───────────────────────────────────────
ok("bad verdict rejected", raises(lambda: fb.add_feedback(m_good, "meh", conn=conn), ValueError))
ok("missing memory rejected", raises(lambda: fb.add_feedback(999999, "useful", conn=conn), ValueError))
ok("neutral usefulness without feedback", fb.usefulness(m_good, conn=conn) == 0.5)
fb.add_feedback(m_good, "useful", "turn:1", conn=conn)
fb.add_feedback(m_good, "useful", "turn:2", conn=conn)
ok("useful raises the signal", fb.usefulness(m_good, conn=conn) == 0.8)
fb.add_feedback(m_bad, "wrong", "turn:1", conn=conn)
ok("wrong drops the signal harder than irrelevant", fb.usefulness(m_bad, conn=conn) == 0.2)
fb.add_feedback(m_bad, "wrong", "turn:2", conn=conn)
fb.add_feedback(m_bad, "wrong", "turn:3", conn=conn)
ok("signal clamps at 0", fb.usefulness(m_bad, conn=conn) == 0.0)

# feedback never deletes anything (acceptance)
ok("memory row untouched by feedback",
   repo.read(m_bad, conn=conn).status is MemoryStatus.ACTIVE)
ok("evidence untouched by feedback",
   count("SELECT count(*) FROM brain_memory_evidence WHERE memory_id=?", (m_bad,)) == 1)

# ranking integration: same topic, wrong-marked memory ranks below useful-marked
r = ret.retrieve("how does the owner plan sprints?", "chat", conn=conn)
ids = [x["memory_id"] for x in r]
ok("feedback reorders retrieval (useful above wrong)",
   m_good in ids and m_bad in ids and ids.index(m_good) < ids.index(m_bad), str(ids))
ok("feedback signal flows into ranking signals",
   next(x for x in r if x["memory_id"] == m_good)["signals"]["feedback"] == 0.8)

# ── influence traces ─────────────────────────────────────────────────────────
n = fb.record_influence([m_good, m_bad], "chat", turn_ref="turn:9",
                        query_hint="how does the owner plan sprints?", conn=conn)
ok("influence recorded for each memory", n == 2
   and count("SELECT count(*) FROM brain_memory_influence WHERE turn_ref='turn:9'") == 2)
trace = fb.influence_of(m_good, conn=conn)
ok("influence_of returns where and why", trace and trace[0]["turn_ref"] == "turn:9"
   and "sprints" in trace[0]["query_hint"] and trace[0]["surface"] == "chat")
ok("record_influence never raises (best-effort contract)",
   fb.record_influence([999999], "chat", conn=conn) in (0, 1))

# context wiring records influence when the flag is on
from core import context_manager as cm  # noqa: E402
owner_flags.set_bool(owner_flags.BRAIN_V2_ENABLED, True)
cm.invalidate()
before = count("SELECT count(*) FROM brain_memory_influence")
m = cm.build_manifest("how does the owner plan sprints?", "chat", [])
ok("brain_recall turn auto-records influence traces",
   any(i.source == "brain_recall" for i in m.items)
   and count("SELECT count(*) FROM brain_memory_influence") > before)
owner_flags.set_bool(owner_flags.BRAIN_V2_ENABLED, False)
cm.invalidate()

# ── action reflection: same gates, pending only ──────────────────────────────
res = fb.reflect_action("create_task", "Owner routinely turns approved specs into PM tasks",
                        "ok", turn_ref="agent:run42", conn=conn)
ok("reflection creates a candidate", res is not None and res.memory_id is not None)
ok("reflection lands pending — success alone never activates",
   res.status is MemoryStatus.PENDING, str(res.status))
row = repo.read(res.memory_id, conn=conn)
ok("reflection pinned inferred + capped confidence",
   row.explicitness is Explicitness.INFERRED and row.confidence == 0.8)
ok("reflection tagged with tool", "action_reflection" in row.tags and "create_task" in row.tags)

# even repeated successes can't promote it (confidence < 0.85 corroboration bar)
res2 = fb.reflect_action("create_task", "The owner routinely turns approved specs into PM tasks",
                         "ok", turn_ref="agent:run43", conn=conn)
ok("repeat reflection merges but never promotes",
   res2.outcome == "merged" and res2.status is MemoryStatus.PENDING)
ok("empty receipt returns None", fb.reflect_action("tool", "   ", conn=conn) is None)
ok("zero untrusted/pending leaks into active from reflections",
   count("SELECT count(*) FROM brain_memory_v2 WHERE status='active' AND "
         "distilled_text LIKE '%PM tasks%'") == 0)

print(f"\n{PASS} checks passed")
