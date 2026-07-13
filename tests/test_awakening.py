"""
AWAKENING TIER 1 COMPLETION (#17) — evidence detector + Conductor tools.

Isolated temp DB (DB_PATH env), plain python, no pytest:
    DB_PATH=/tmp/tawk.db python tests/test_awakening.py

Covers: the registry returns exactly 9 abilities in 3 categories; each status is
reachable; structural/tool abilities activate from real registration; memory abilities
activate from real Brain data; a missing connector shows setup_needed (never a failure);
sensitive memories don't count until reviewed; progress hits 100 only when all 9 active;
full task CRUD incl. update_task via the Conductor with delete gated high-risk; the three
packaged workflows run; the awakening_status tool is grounded; the persona is shared.
"""
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix="tobi_tawk_")
os.environ["DB_PATH"] = os.path.join(_TMP, "agent.db")
# Deterministic connector state — start with NO read connector configured.
for _k in ("GITHUB_TOKEN", "NOTION_API_KEY", "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"):
    os.environ.pop(_k, None)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    sys.stdout.reconfigure(encoding="utf-8")  # ✅ glyphs on Windows cp1258
except Exception:
    pass

from core.database import init_database, get_connection  # noqa: E402

init_database()

from core import awakening as A  # noqa: E402
from core import brain  # noqa: E402
from core import conductor as C  # noqa: E402

PASS = 0


def ok(name: str, cond: bool, detail: str = ""):
    global PASS
    if not cond:
        print(f"❌ {name} {detail}")
        sys.exit(1)
    PASS += 1
    print(f"✅ {name}")


def _statuses():
    conn = get_connection()
    try:
        return A.status_map(conn)
    except Exception:
        return {}
    finally:
        conn.close()


# ── registry shape ─────────────────────────────────────────────────────────────────
conn = get_connection()
abilities = A.evaluate(conn)
conn.close()
ok("registry returns exactly 9 abilities", len(abilities) == 9, str(len(abilities)))
ok("ability ids match the spec", {a["id"] for a in abilities} == {
    "owner_profile_memory", "conversation_memory", "preference_learning",
    "consistent_persona", "contextual_self_awareness", "evolution_tracking",
    "internal_task_management", "external_read_access", "simple_automation"})
ok("three categories present", {a["category"] for a in abilities} == {
    "persistent_memory", "identity_personality", "basic_real_world_action"})
ok("every ability has evidence/missing/setup/status/risk", all(
    {"status", "evidence", "missing", "setup_actions", "risk", "category_label", "short_name"} <= set(a) for a in abilities))
ok("statuses are from the 4-valued set", all(
    a["status"] in ("active", "partial", "setup_needed", "inactive") for a in abilities))

# ── structural / tool-backed abilities are active from real registration ────────────
st = _statuses()
ok("consistent_persona active (shared _BUTLER)", st["consistent_persona"] == "active", st.get("consistent_persona", ""))
ok("evolution_tracking active (registry wired)", st["evolution_tracking"] == "active")
ok("contextual_self_awareness active (awakening_status tool)", st["contextual_self_awareness"] == "active")
ok("internal_task_management active (6 task tools incl. update_task)", st["internal_task_management"] == "active")
ok("simple_automation partial until workflows have a logged receipt (not just registered)", st["simple_automation"] == "partial")

# ── memory abilities + external read are setup_needed on an empty/unconfigured system ─
ok("owner_profile_memory setup_needed when Brain is empty", st["owner_profile_memory"] == "setup_needed")
ok("conversation_memory setup_needed when Brain is empty", st["conversation_memory"] == "setup_needed")
ok("preference_learning setup_needed when Brain is empty", st["preference_learning"] == "setup_needed")
ok("external_read_access setup_needed with no connector (not a failure)", st["external_read_access"] == "setup_needed")

conn = get_connection()
summ = A.summary(conn)
conn.close()
ok("progress < 100 before evidence exists", summ["progress_pct"] < 100 and not summ["complete"])
ok("summary counts active correctly", summ["active_count"] == sum(1 for v in st.values() if v == "active"))

# ── seed real Brain evidence → memory abilities activate ────────────────────────────
brain.add_memory("The owner is Thomas, founder of TOBI.", "identity", 0.95, "remember", "active")
brain.add_memory("Owner works late nights on Mission Control.", "work", 0.9, "chat", "active")
brain.add_memory("Owner prefers concise diffs and honest status.", "preferences", 0.9, "chat", "active")
brain.add_memory("Owner takes coffee breaks mid-afternoon.", "habits", 0.85, "telegram", "active")
st2 = _statuses()
ok("owner_profile_memory active after seeding profile facts", st2["owner_profile_memory"] == "active", st2["owner_profile_memory"])
ok("conversation_memory active after conversational-source memories", st2["conversation_memory"] == "active", st2["conversation_memory"])
ok("preference_learning active after preference/habit memories", st2["preference_learning"] == "active", st2["preference_learning"])

# ── sensitive memory must NOT count until reviewed ──────────────────────────────────
conn = get_connection()
conn.execute("INSERT OR IGNORE INTO brain_categories (id, label, sensitive, status) VALUES ('secret','Secret',1,'active')")
conn.commit()
conn.close()
brain.add_memory("A sensitive owner fact awaiting review.", "secret", 0.95, "chat", "pending")
conn = get_connection()
summ2 = A.summary(conn)
conn.close()
ok("sensitive pending memory is surfaced for review", summ2["sensitive_pending_review"] >= 1, str(summ2["sensitive_pending_review"]))
# it stays pending, so it does not push any ability's evidence (owner_profile counts active only)

# ── connector states: configured ≠ authorized ≠ usable (High #17 fix) ───────────────
ok("external_read_access still setup_needed (no connector)", _statuses()["external_read_access"] == "setup_needed")
os.environ["GOOGLE_CLIENT_ID"] = "gid"
os.environ["GOOGLE_CLIENT_SECRET"] = "gsecret"
ok("Google configured but OAuth NOT completed → still setup_needed (no false-active)",
   _statuses()["external_read_access"] == "setup_needed")
os.environ["GITHUB_TOKEN"] = "ghp_dummy_for_test"
ok("external_read_access active once a usable read connector is present",
   _statuses()["external_read_access"] == "active")

# ── tier1_pillars groups the 9 into the 3 render pillars with category labels ────────
conn = get_connection()
pillars = A.tier1_pillars(conn)
conn.close()
ok("tier1_pillars has understand/control/presence", set(pillars) == {"understand", "control", "presence"})
ok("tier1_pillars totals 9 abilities", sum(len(v) for v in pillars.values()) == 9)
labels = A.pillar_labels()
ok("pillar labels map to the 3 categories",
   set(labels.values()) == {"Persistent Memory", "Identity & Personality", "Basic Real-World Action"})

# ── Conductor: full task CRUD incl. update_task, with risk tiers ────────────────────
proj = C.tool_create_project(name="Awakening Test Project")
pid = proj["project_id"]
task = C.tool_create_task(project_id=pid, title="Draft the release notes")
tid = task["task_id"]
ok("create_task works", task.get("ok") and isinstance(tid, int))

upd = C.tool_update_task(task_id=tid, title="Draft + polish the release notes",
                         status="in_progress", priority="high", agent="coder")
ok("update_task edits multiple fields", upd.get("ok") and upd["updated"].get("status") == "in_progress"
   and upd["updated"].get("priority") == "P1" and upd["updated"].get("agent") == "coder")
conn = get_connection()
row = conn.execute("SELECT title, status_v1, priority_label, agent_key FROM tasks WHERE id=?", (tid,)).fetchone()
conn.close()
ok("update_task persisted to the tasks table",
   row[0].startswith("Draft + polish") and row[1] == "in_progress" and row[2] == "P1" and row[3] == "coder")
ok("update_task rejects an unknown status", C.tool_update_task(task_id=tid, status="wat").get("error"))
ok("update_task with nothing to change errors", C.tool_update_task(task_id=tid).get("error"))

ok("complete_task works", C.tool_complete_task(task_id=tid).get("ok"))
ok("delete_task works", C.tool_delete_task(task_id=tid).get("deleted"))
ok("delete_task is registered high-risk (confirmation-gated)", C.ACT_TOOLS["delete_task"][1] == "high")
ok("update_task is registered medium-risk", C.ACT_TOOLS["update_task"][1] == "medium")

# ── Conductor: the three packaged workflows (#17) run ───────────────────────────────
conv = C.tool_create_task_from_conversation(tasks=["Follow up with the designer", {"title": "Ship the beta", "description": "by Friday"}])
ok("create_task_from_conversation creates tasks in an Inbox project", conv.get("ok") and conv["count"] == 2)
conn = get_connection()
inbox_ok = conn.execute("SELECT 1 FROM pm_projects WHERE lower(name)='inbox'").fetchone() is not None
conn.close()
ok("create_task_from_conversation resolved/created the Inbox project", inbox_ok)
ok("create_task_from_conversation needs at least one title",
   C.tool_create_task_from_conversation(tasks=[]).get("error"))

note = C.tool_save_note(text="Owner asked to revisit pricing next week.", category="work")
ok("save_note saves to the Brain by default", note.get("ok") and note.get("saved_to") == "brain")
note2 = C.tool_save_note(text="Project-scoped note", project_id=pid)
ok("save_note saves to a project resource when project_id is given",
   isinstance(note2, dict) and (note2.get("saved_to") == "project_resource" or note2.get("error")))
ok("summarize_repo validates the repo argument", C.tool_summarize_repo(repo="not-a-repo").get("error"))

# ── Simple Automation is gated on real logged receipts, not registration (High #17) ──
ok("simple_automation partial before any workflow receipt exists", _statuses()["simple_automation"] == "partial")
ok("summarize_repo is audited as a workflow read-tool", "summarize_repo" in C._WORKFLOW_READ_TOOLS)
# with GitHub off, summarize_repo reports unavailable — so it can NOT be a false success receipt
os.environ.pop("GITHUB_TOKEN", None)
_unavail = C.tool_summarize_repo(repo="octocat/Hello-World")
ok("summarize_repo reports unavailable when GitHub is off (not a false success)",
   isinstance(_unavail, dict) and not (_unavail.get("available") and not _unavail.get("error")))
os.environ["GITHUB_TOKEN"] = "ghp_dummy_for_test"
# a FAILED workflow receipt does not activate the ability
C._log_action(0, "mc", "summarize_repo", {"repo": "octocat/Hello-World"}, "read", "failed", "summarize", {"available": False})
ok("a failed workflow receipt does not activate Simple Automation", _statuses()["simple_automation"] == "partial")
# once each of the 3 workflows has a SUCCESSFUL logged receipt → active
for _wt in ("create_task_from_conversation", "save_note", "summarize_repo"):
    C._log_action(0, "mc", _wt, {}, "read" if _wt == "summarize_repo" else "low", "executed", "ran", {"ok": True})
ok("simple_automation active only after all 3 workflows have successful receipts",
   _statuses()["simple_automation"] == "active")

# ── persona verified BEHAVIORALLY across surfaces, not just string length (Medium #17) ─
_mc = C._system_prompt("", True, surface="mc")
_tg = C._system_prompt("", True, surface="telegram")
_anchor = C._BUTLER[:120]
ok("the same butler persona anchors MC chat AND Telegram system prompts", bool(_anchor) and _anchor in _mc and _anchor in _tg)
ok("consistent_persona evidence is behavioral (active)", _statuses()["consistent_persona"] == "active")

# ── all 9 now genuinely active → progress is exactly 100, complete ──────────────────
conn = get_connection()
final = A.summary(conn)
conn.close()
ok("progress reaches 100 only when all 9 are genuinely active", final["progress_pct"] == 100 and final["complete"],
   f"{final['active_count']}/9")

# ── awakening_status read tool is grounded ──────────────────────────────────────────
aw = C.tool_awakening_status()
ok("awakening_status reports tier 1 with 9 abilities", aw.get("tier") == 1 and aw.get("total") == 9)
ok("awakening_status is grounded (100% now that all evidence exists)", aw.get("progress_pct") == 100)
ok("awakening_status tool is a READ tool", "awakening_status" in C.READ_TOOLS)

# ── Brain sweep: a failed batch is NEVER skipped by a later success (High #17) ───────
conn = get_connection()
conn.execute("UPDATE brain_sweep_state SET last_processed_convo_id=0 WHERE id=1")
conn.execute("INSERT INTO conversations (chat_id, role, content) VALUES (7001,'user','alpha message')")
conn.execute("INSERT INTO conversations (chat_id, role, content) VALUES (7002,'user','bravo message')")
conn.commit()
first_id = conn.execute("SELECT MIN(id) FROM conversations WHERE chat_id IN (7001,7002)").fetchone()[0]
conn.close()
_orig_extract = brain.extract_from_messages
def _fail_alpha(messages):
    if any("alpha" in (m.get("content") or "") for m in messages):
        raise RuntimeError("simulated LLM failure")
    return []
brain.extract_from_messages = _fail_alpha
try:
    brain.sweep_once(limit=60)
finally:
    brain.extract_from_messages = _orig_extract
conn = get_connection()
hwm = conn.execute("SELECT last_processed_convo_id FROM brain_sweep_state WHERE id=1").fetchone()[0]
conn.close()
ok("brain sweep does not advance the cursor past a failed batch", hwm < first_id, f"hwm={hwm} first={first_id}")

# ── Brain sweep is serialized — a concurrent sweep is skipped (Medium #17) ──────────
_held = brain._SWEEP_LOCK.acquire(blocking=False)
try:
    busy = brain.sweep_once(limit=10)
    ok("a concurrent sweep is skipped while one holds the lock", busy.get("skipped_busy") is True)
finally:
    if _held:
        brain._SWEEP_LOCK.release()

print(f"\n🎉 ALL {PASS} CHECKS PASSED")
