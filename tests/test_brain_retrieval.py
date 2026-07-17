"""
Brain Memory V2 retrieval (queue #20, T07) — stable behavior profile (≤800 tok,
versioned), ranked task retrieval (spec weights + precedence + budgets),
scope/relevance exclusion, hedging, chips, and flag-gated context wiring.

Plain python, no pytest, isolated temp DB:
    python tests/test_brain_retrieval.py
"""
import os
import sys
import tempfile

os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="tobi_bret_"), "agent.db")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from core.database import init_database, get_connection  # noqa: E402
from core import vault, owner_flags  # noqa: E402
from core import brain_repository as repo  # noqa: E402
from core import brain_retrieval as ret  # noqa: E402
from core.brain_contracts import (  # noqa: E402
    MemoryCandidate, MemoryType, ScopeType, Authority, Explicitness, MemoryStatus,
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


def seed(text, mtype=MemoryType.FACT, status=MemoryStatus.ACTIVE, **kw):
    base = dict(distilled_text=text, memory_type=mtype, explicitness=Explicitness.EXPLICIT,
                confidence=0.9, durability=1, actionability=1, specificity=1, source_strength=1)
    base.update(kw)
    return repo.save(MemoryCandidate(**base), status=status, conn=conn)


# ── seeds ────────────────────────────────────────────────────────────────────
seed("Owner's name is Thomas", MemoryType.IDENTITY, confidence=0.95)
hard_rule = seed("Never deploy on Fridays", MemoryType.BEHAVIOR_RULE,
                 authority=Authority.HARD)                      # owner-approved → active
seed("Owner prefers concise, direct replies", MemoryType.PREFERENCE, durability=0.9)
seed("Owner casually liked one taco place", MemoryType.PREFERENCE, durability=0.3)
seed("Owner might like jazz music", MemoryType.FACT, status=MemoryStatus.PENDING,
     explicitness=Explicitness.INFERRED)
seed("Owner's favorite editor is VS Code", MemoryType.FACT)
seed("Owner likes deploying early in the week", MemoryType.PREFERENCE, durability=0.8)
alpha = seed("Use tabs for indentation in the alpha repo", MemoryType.PREFERENCE,
             scope_type=ScopeType.PROJECT, scope_key="alpha", durability=0.8)
seed("Owner generally prefers spaces for indentation", MemoryType.PREFERENCE, durability=0.8)
lowconf = seed("Owner apparently drafts posts in Notion first", MemoryType.FACT, confidence=0.7)

# ── stage 1: stable profile ──────────────────────────────────────────────────
text, ver = ret.stable_profile(conn=conn)
ok("profile contains identity", "IDENTITY: Owner's name is Thomas" in text)
ok("profile contains owner-approved hard rule as RULE",
   "RULE (owner-approved): Never deploy on Fridays" in text)
ok("profile contains durable preference", "Owner prefers concise, direct replies" in text)
ok("profile excludes non-durable preference", "taco" not in text)
ok("profile excludes pending memories", "jazz" not in text)
ok("profile is versioned", len(ver) == 12)
seed("Owner also goes by binhvu284 online", MemoryType.IDENTITY)
text2, ver2 = ret.stable_profile(conn=conn)
ok("profile version changes when the store changes", ver2 != ver and "binhvu284" in text2)

# ── stage 2: retrieval ───────────────────────────────────────────────────────
r = ret.retrieve("which editor should I set up for the owner?", "chat", conn=conn)
ok("relevant memory retrieved", any("VS Code" in x["text"] for x in r), str([x["text"] for x in r]))
ok("pending memory never retrieved", all("jazz" not in x["text"] for x in r))

r = ret.retrieve("kubernetes cluster networking latency", "chat", conn=conn)
ok("irrelevant memory stays out (relevance floor)", all("VS Code" not in x["text"] for x in r), str(len(r)))

# scope: excluded outright for other scopes; scoped outranks global inside its scope
r = ret.retrieve("tabs or spaces for indentation in the repo?", "chat", conn=conn)
ok("scoped memory never leaks into global context", all(x["memory_id"] != alpha for x in r))
r = ret.retrieve("tabs or spaces for indentation in the repo?", "chat",
                 scope_type=ScopeType.PROJECT, scope_key="alpha", conn=conn)
ids = [x["memory_id"] for x in r]
ok("scoped memory retrieved inside its scope", alpha in ids)
ok("scoped soft precedes global soft (precedence 5 < 6)",
   ids.index(alpha) < ids.index(next(x["memory_id"] for x in r if "spaces" in x["text"])))

# precedence: hard rule before soft preference on the same topic
r = ret.retrieve("should I deploy this Friday afternoon?", "chat", conn=conn)
ok("hard rule retrieved for deploy query", any(x["memory_id"] == hard_rule for x in r))
hard_pos = next(i for i, x in enumerate(r) if x["authority"] == "hard")
soft_pos = [i for i, x in enumerate(r) if x["authority"] == "soft"]
ok("hard rule precedes soft memories", not soft_pos or hard_pos < min(soft_pos))
ok("signals + spec weights present",
   set(r[0]["signals"]) == {"semantic", "scope", "authority", "quality", "confidence",
                            "recency", "feedback"} and ret.RANK_WEIGHTS["semantic"] == 35)

# hedging: low confidence never presented as fact
r = ret.retrieve("where does the owner draft posts?", "chat", conn=conn)
low = next(x for x in r if x["memory_id"] == lowconf)
ok("low-confidence memory hedged", low["hedged"] is True)
block, chips = ret.context_block("where does the owner draft posts?", "chat", conn=conn)
ok("hedged memory rendered as (unconfirmed)", "(unconfirmed) Owner apparently drafts" in block)
ok("context block states memory grants no permissions", "grants no permissions" in block)
ok("chips emitted for every used memory", len(chips) == len(r)
   and all({"memory_id", "text", "confidence", "hedged", "evidence"} <= set(c) for c in chips))

# budgets: chat 6 / agent 10
for i in range(8):
    seed(f"Owner delivery queue workflow note number {i} for planning", MemoryType.FACT)
r = ret.retrieve("delivery queue workflow planning", "chat", conn=conn)
ok("chat budget caps at 6 memories", len(r) == 6, str(len(r)))
r = ret.retrieve("delivery queue workflow planning", "agent", conn=conn)
ok("agent budget allows more (up to 10)", 6 < len(r) <= 10, str(len(r)))

# sensitive: active-but-locked drops out of profile and retrieval entirely
sens = seed("Owner's home safe corner code word is RETRIEVE_SECRET_7788", MemoryType.FACT,
            sensitive=True, status=MemoryStatus.PENDING)
repo.set_status(sens, MemoryStatus.ACTIVE, conn=conn)   # owner-approved
r = ret.retrieve("what is the owner's safe code word?", "chat", conn=conn)
ok("sensitive active memory retrievable while unlocked", any(x["memory_id"] == sens for x in r))
vault.lock()
r = ret.retrieve("what is the owner's safe code word?", "chat", conn=conn)
ok("locked vault: sensitive memory excluded from retrieval", all(x["memory_id"] != sens for x in r))
ok("locked vault: sensitive memory excluded from profile",
   "RETRIEVE_SECRET_7788" not in ret.stable_profile(conn=conn)[0])
vault.unlock(conn, "master-pass-123456")

# ── flag-gated context wiring ────────────────────────────────────────────────
from core import context_manager as cm  # noqa: E402
cm.invalidate()
ok("flag defaults off", owner_flags.brain_v2_mode() == "off")
m = cm.build_manifest("which editor should I set up?", "chat", [])
ok("flag off: no brain_recall item", all(i.source != "brain_recall" for i in m.items))

owner_flags.set_bool(owner_flags.BRAIN_V2_ENABLED, True)
cm.invalidate()
m = cm.build_manifest("which editor should I set up for the owner?", "chat", [])
owner_mem = next((i for i in m.items if i.source == "owner_memory"), None)
recall = next((i for i in m.items if i.source == "brain_recall"), None)
ok("flag on: owner_memory served from the V2 profile",
   owner_mem is not None and "IDENTITY: Owner's name is Thomas" in owner_mem.content)
ok("flag on: brain_recall item with chips metadata",
   recall is not None and recall.metadata.get("chips") and "VS Code" in recall.content)
pc = cm.prompt_context(m)
ok("recall block reaches TURN CONTEXT; profile rides its own slot",
   "Owner memory recall" in pc and "IDENTITY: Owner's name is Thomas" not in pc)

owner_flags.set_bool(owner_flags.BRAIN_V2_ENABLED, False)
cm.invalidate()
m = cm.build_manifest("which editor should I set up?", "chat", [])
ok("rollback: flag off restores legacy manifest (no recall item)",
   all(i.source != "brain_recall" for i in m.items))

# ── profile budget: whole memories only, never sliced ────────────────────────
for i in range(40):
    seed(f"Owner identity fact number {i}: " + ("detail " * 40), MemoryType.IDENTITY)
text, _ = ret.stable_profile(conn=conn)
ok("profile respects the 800-token budget", ret._estimate_tokens(text) <= ret.PROFILE_TOKEN_BUDGET + 40,
   str(ret._estimate_tokens(text)))
ok("profile lines are whole memories (no mid-sentence slice)",
   all(line.endswith(("Thomas", "Fridays", "replies", "online")) or line.rstrip().endswith("detail")
       for line in text.split("\n")), text.split("\n")[-1][-60:])

print(f"\n{PASS} checks passed")
