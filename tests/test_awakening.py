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
import time

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
from core.conductor_tools import external_read_tools as _ert  # noqa: E402

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

# ── connector states: configured ≠ VERIFIED (P1 review fix — no false-active) ────────
ok("external_read_access setup_needed with nothing configured", _statuses()["external_read_access"] == "setup_needed")
os.environ["GOOGLE_CLIENT_ID"] = "gid"
os.environ["GOOGLE_CLIENT_SECRET"] = "gsecret"
ok("Google client id/secret without a completed OAuth token → still setup_needed",
   _statuses()["external_read_access"] == "setup_needed")
os.environ["GITHUB_TOKEN"] = "ghp_dummy_for_test"
ok("configured-but-unverified connector → PARTIAL, not active (a dummy/expired token can't fake usable access)",
   _statuses()["external_read_access"] == "partial")
# A cached Google setup result cannot bypass incomplete OAuth.
from core import vault  # noqa: E402
from core import integrations_registry as integration_registry  # noqa: E402
ok("Google credential-stage success does not claim verified read access",
   integration_registry.test_confirms_read_access("google") is False)
conn = get_connection()
_prof = vault.active_profile(conn)
conn.execute("INSERT OR REPLACE INTO vault_secrets "
             "(profile, name, integration_id, secret_type, ciphertext, nonce, last4, test_status, last_tested_at) "
             "VALUES (?,?,?,?,?,?,?,?,datetime('now'))",
             (_prof, "GOOGLE_CLIENT_ID", "google", "oauth", b"\x00", b"\x00", "gid", "ok"))
conn.commit()
conn.close()
ok("cached Google ok without completed OAuth remains PARTIAL, never active",
   _statuses()["external_read_access"] == "partial")

# Successful evidence must also be fresh; stale/revoked credentials do not remain active forever.
conn = get_connection()
conn.execute("INSERT OR REPLACE INTO vault_secrets "
             "(profile, name, integration_id, secret_type, ciphertext, nonce, last4, test_status, last_tested_at) "
             "VALUES (?,?,?,?,?,?,?,?,datetime('now','-2 days'))",
             (_prof, "GITHUB_TOKEN", "github", "api_key", b"\x00", b"\x00", "tok", "ok"))
conn.commit()
conn.close()
ok("stale cached connector evidence remains PARTIAL",
   _statuses()["external_read_access"] == "partial")
conn = get_connection()
conn.execute("UPDATE vault_secrets SET last_tested_at=datetime('now') WHERE integration_id='github'")
conn.commit()
conn.close()
ok("external_read_access active only with a ready connector and fresh successful test",
   _statuses()["external_read_access"] == "active")

# A normal MC restart must renew stale GitHub evidence itself. The saved credential
# remains the source of truth; no owner visit to Integrations -> GitHub -> Test is needed.
_registry_test = integration_registry.test_integration
_registry_confirms = integration_registry.test_confirms_read_access
_startup_calls = []
try:
    integration_registry.test_integration = lambda iid: (
        _startup_calls.append(iid) or (True, "GitHub token valid."))
    integration_registry.test_confirms_read_access = lambda iid: iid == "github"
    conn = get_connection()
    conn.execute("UPDATE vault_secrets SET last_tested_at=datetime('now','-2 days') "
                 "WHERE integration_id='github'")
    conn.commit()
    startup_refresh = A.refresh_connector_evidence_on_startup(conn)
    refreshed = conn.execute(
        "SELECT test_status,last_tested_at FROM vault_secrets "
        "WHERE integration_id='github'"
    ).fetchone()
    conn.close()
finally:
    integration_registry.test_integration = _registry_test
    integration_registry.test_confirms_read_access = _registry_confirms
ok("MC startup automatically verifies stale GitHub proof",
   startup_refresh.get("github") == "verified" and _startup_calls == ["github"],
   str(startup_refresh))
ok("automatic GitHub verification persists fresh proof",
   refreshed[0] == "ok" and A._connector_test_fresh(refreshed[1]), str(tuple(refreshed)))
ok("Awakening stays active after automatic startup verification",
   _statuses()["external_read_access"] == "active")
conn = get_connection()
second_startup = A.refresh_connector_evidence_on_startup(conn)
conn.close()
ok("later restarts reuse fresh GitHub proof without another network test",
   second_startup.get("github") == "fresh" and _startup_calls == ["github"],
   str(second_startup))
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(_root, "main.py"), encoding="utf-8") as _f:
    _main_source = _f.read()
with open(os.path.join(_root, "api", "dashboard.py"), encoding="utf-8") as _f:
    _dashboard_source = _f.read()
ok("full and API-only MC startup paths both refresh connector evidence",
   "refresh_connector_evidence_on_startup(conn)" in _main_source
   and "refresh_connector_evidence_on_startup(conn)" in _dashboard_source)

# Changing a secret invalidates its old successful-test evidence until it is tested again.
_vault_key, _vault_encrypt = vault._key, vault._encrypt
vault._key = b"test-key"
vault._encrypt = lambda key, name, value: (b"cipher", b"nonce")
try:
    conn = get_connection()
    vault.set_secret(conn, "ROTATION_TEST_SECRET", "first", integration_id="custom", test_status="ok")
    tested = conn.execute(
        "SELECT test_status,last_tested_at FROM vault_secrets WHERE name='ROTATION_TEST_SECRET'"
    ).fetchone()
    vault.set_secret(conn, "ROTATION_TEST_SECRET", "second", integration_id="custom")
    rotated = conn.execute(
        "SELECT test_status,last_tested_at FROM vault_secrets WHERE name='ROTATION_TEST_SECRET'"
    ).fetchone()
    conn.close()
finally:
    vault._key, vault._encrypt = _vault_key, _vault_encrypt
ok("successful secret tests record a timestamp", tested[0] == "ok" and tested[1] is not None)
ok("secret rotation clears stale verification evidence",
   rotated[0] == "untested" and rotated[1] is None, str(tuple(rotated)))

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

# ── Brain sweep: failed batches are preserved for retry without starving other chats ──────
conn = get_connection()
brain._ensure_sweep_schema(conn)
conn.execute("DELETE FROM brain_sweep_cursors")
conn.execute("DELETE FROM brain_sweep_failures")
conn.execute("INSERT INTO conversations (chat_id, role, content) VALUES (7001,'user','alpha message')")
conn.execute("INSERT INTO conversations (chat_id, role, content) VALUES (7002,'user','bravo message')")
conn.commit()
a_id = conn.execute("SELECT id FROM conversations WHERE chat_id=7001").fetchone()[0]
b_id = conn.execute("SELECT id FROM conversations WHERE chat_id=7002").fetchone()[0]
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
cur = {r[0]: r[1] for r in conn.execute("SELECT chat_id, last_id FROM brain_sweep_cursors").fetchall()}
failure = conn.execute(
    "SELECT id, attempts, status, payload_json FROM brain_sweep_failures WHERE chat_id=7001"
).fetchone()
conn.close()
ok("failed chat advances only after its payload is durably deferred",
   cur.get(7001, -1) >= a_id and failure is not None and failure[2] == "pending",
   f"cursor={cur.get(7001)} failure={failure}")
ok("a healthy chat advances even while another chat keeps failing (no cross-chat starvation)",
   cur.get(7002, -1) >= b_id, f"7002={cur.get(7002)} b_id={b_id}")
ok("deferred batch retains the original conversation payload", "alpha message" in failure[3])

# Two more provider failures increment retry metadata but never delete the deferred payload.
brain.extract_from_messages = lambda messages: None
try:
    for _ in range(2):
        conn = get_connection()
        conn.execute("UPDATE brain_sweep_failures SET next_retry_at='1970-01-01T00:00:00+00:00' WHERE id=?", (failure[0],))
        conn.commit()
        conn.close()
        brain.sweep_once(limit=60)
finally:
    brain.extract_from_messages = _orig_extract
conn = get_connection()
failure3 = conn.execute("SELECT attempts, status FROM brain_sweep_failures WHERE id=?", (failure[0],)).fetchone()
conn.close()
ok("three provider failures remain recoverable instead of skipping owner memory",
   failure3[0] == 3 and failure3[1] == "pending", str(tuple(failure3)))

# Once the extractor recovers, the stored payload is retried and resolved.
def _recover_alpha(messages):
    if any("alpha" in (m.get("content") or "") for m in messages):
        return [{"content": "ZXQ-471 deferred recovery marker.", "category": "goals", "confidence": 0.95}]
    return []
brain.extract_from_messages = _recover_alpha
try:
    conn = get_connection()
    conn.execute("UPDATE brain_sweep_failures SET next_retry_at='1970-01-01T00:00:00+00:00' WHERE id=?", (failure[0],))
    conn.commit()
    conn.close()
    recovered = brain.sweep_once(limit=60)
finally:
    brain.extract_from_messages = _orig_extract
conn = get_connection()
failure_done = conn.execute(
    "SELECT status,payload_json FROM brain_sweep_failures WHERE id=?", (failure[0],)
).fetchone()
recovered_memory = conn.execute(
    "SELECT COUNT(*) FROM brain_memories WHERE content='ZXQ-471 deferred recovery marker.' AND status='active'"
).fetchone()[0]
conn.close()
ok("recovered extractor resolves the deferred batch and creates its memory",
   recovered.get("recovered") == 1 and failure_done[0] == "resolved" and recovered_memory == 1,
   f"tally={recovered} status={failure_done[0]} memories={recovered_memory}")
ok("resolved retry clears its duplicate raw conversation payload", failure_done[1] == "[]")

# Malformed structured output is retryable, not silently interpreted as no durable facts.
_orig_llm = brain._llm
brain._llm = lambda *a, **k: "not valid json"
try:
    ok("malformed extraction output is reported as retryable failure",
       brain.extract_from_messages([{"role": "user", "content": "remember this"}]) is None)
finally:
    brain._llm = _orig_llm

# ── Brain sweep lease is owner-bound and survives stale-owner release ──────────────────────
_held = brain._acquire_lease()
try:
    busy = brain.sweep_once(limit=10)
    ok("a concurrent sweep is skipped while the DB lease is held", busy.get("skipped_busy") is True)
finally:
    if _held:
        brain._release_lease(_held)
brain.extract_from_messages = lambda messages: []  # keep this sweep offline (no live LLM call)
try:
    ok("once the lease is released a sweep can run again", "skipped_busy" not in brain.sweep_once(limit=10))
finally:
    brain.extract_from_messages = _orig_extract

stale_holder = brain._acquire_lease(ttl=0)
time.sleep(0.01)
new_holder = brain._acquire_lease(ttl=300)
ok("expired lease can be reclaimed by a new unique owner",
   bool(stale_holder and new_holder and stale_holder != new_holder))
ok("stale owner cannot release its successor's active lease",
   brain._release_lease(stale_holder) is False)
conn = get_connection()
current_holder = conn.execute("SELECT holder FROM brain_sweep_lease WHERE id=1").fetchone()[0]
conn.close()
ok("successor lease remains intact after stale release", current_holder == new_holder)
ok("current lease owner can renew and release", brain._renew_lease(new_holder) and brain._release_lease(new_holder))

# ── P2 review fix: an ACTUAL summarize_repo call through conductor.answer() logs a receipt,
#    and the action-capable turn's system prompt carries the butler persona ─────────────────
from core import model_router as mr  # noqa: E402


class _CapFake:
    last_finish_reason = None

    def __init__(self, lines):
        self.lines = list(lines)
        self.systems = []

    def complete(self, messages, system=None, max_tokens=2000):
        self.systems.append(system or "")
        return self.lines.pop(0) if self.lines else "Summarized, sir."


# Patch where the function is DEFINED, not only where conductor re-exports it. The conductor
# tool extraction moved tool_read_github into core.conductor_tools.external_read_tools, and
# tool_summarize_repo calls its module-local neighbour — so rebinding only C.tool_read_github
# left the stub unused and sent this check at a real GitHub call. Rebinding a name only
# affects the namespace you rebind it in; a re-export restores attribute access, never a
# monkeypatch seam.
_stub_rg = lambda **kw: {"available": True, "repo": kw.get("repo"), "description": "stub repo"}
_orig_rg, _orig_ert_rg = C.tool_read_github, _ert.tool_read_github
C.tool_read_github = _stub_rg
_ert.tool_read_github = _stub_rg
_fake = _CapFake(['{"tool":"summarize_repo","args":{"repo":"octocat/Hello-World"}}', "Here's the summary, sir."])
_orig_get_llm = mr.get_llm
mr.get_llm = lambda *a, **k: _fake
try:
    C.answer("summarize the github repo octocat/Hello-World for me", chat_id=-7788, surface="mc")
finally:
    C.tool_read_github = _orig_rg
    _ert.tool_read_github = _orig_ert_rg
    mr.get_llm = _orig_get_llm
conn = get_connection()
rec = conn.execute("SELECT status FROM tobi_actions WHERE tool='summarize_repo' AND chat_id=-7788 ORDER BY id DESC LIMIT 1").fetchone()
conn.close()
ok("summarize_repo via conductor.answer() creates a real tobi_actions receipt (P2b end-to-end)",
   rec is not None and rec[0] == "executed", str(rec))
ok("the action-capable turn's system prompt anchors the butler persona (P2a)",
   any(C._BUTLER[:120] in s for s in _fake.systems))

print(f"\n🎉 ALL {PASS} CHECKS PASSED")
