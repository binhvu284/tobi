"""
PROJECT RESOURCE ACCESS — the "can't enter a project / read its resources" fix.

Isolated temp DB (DB_PATH env), plain python, no pytest:
    DB_PATH=/tmp/tres.db python tests/test_resource_access.py

Covers the two root causes behind the reported bug:
  B (capability): list_project_resources enumerates a project's uploaded resources; read_resource
    returns one resource's text by name or id (binary → metadata only, graceful unknown-name error);
    search_project_resources with no query returns the inventory instead of erroring.
  A (robustness): route_turn advertises the resource read tools for a project-read turn; and a
    known read-only tool called OUTSIDE the turn's route scope is ADMITTED on demand (not
    hard-denied), so a regex mis-route can no longer dead-end a legitimate read flow.
"""
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix="tobi_tres_")
os.environ["DB_PATH"] = os.path.join(_TMP, "agent.db")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    sys.stdout.reconfigure(encoding="utf-8")  # ✅ glyphs on Windows cp1258
except Exception:
    pass

from core.database import init_database, get_connection  # noqa: E402

init_database()

from core import conductor as C  # noqa: E402
from core.chat_runtime import route_turn, TurnRequest  # noqa: E402

PASS = 0


def ok(name: str, cond: bool, detail: str = ""):
    global PASS
    if not cond:
        print(f"❌ {name} {detail}")
        sys.exit(1)
    PASS += 1
    print(f"✅ {name}")


# ── seed: one project with a readable doc + a binary (no-text) resource ─────────────
conn = get_connection()
conn.execute("INSERT INTO pm_projects (name, status, progress_pct) VALUES (?,?,?)",
             ("Monolith Test", "active", 0))
PID = conn.execute("SELECT id FROM pm_projects WHERE name=?", ("Monolith Test",)).fetchone()[0]
conn.execute(
    "INSERT INTO pm_resources (project_id, kind, name, ext, source, rtype, size_bytes, text_content, created_by) "
    "VALUES (?,?,?,?,?,?,?,?,?)",
    (PID, "file", "Roadmap.md", "md", "device", "doc", 42,
     "Q3 roadmap: ship resource reader. Q4: harden the router.", "user"))
conn.execute(
    "INSERT INTO pm_resources (project_id, kind, name, ext, source, rtype, size_bytes, text_content, created_by) "
    "VALUES (?,?,?,?,?,?,?,?,?)",
    (PID, "file", "diagram.png", "png", "device", "image", 999, None, "user"))
conn.commit()
conn.close()

# ── B: list_project_resources enumerates what the owner uploaded ────────────────────
inv = C.tool_list_project_resources(project="Monolith Test")
ok("list_project_resources returns the project's uploaded resources",
   inv.get("count") == 2 and {r["name"] for r in inv["resources"]} == {"Roadmap.md", "diagram.png"},
   str(inv))
_by_name = {r["name"]: r for r in inv["resources"]}
ok("list marks readable vs non-readable resources",
   _by_name["Roadmap.md"]["readable"] is True and _by_name["diagram.png"]["readable"] is False)
ok("list_project_resources on an unknown project errors gracefully (no crash)",
   bool(C.tool_list_project_resources(project="Nope").get("error")))

# ── B: read_resource returns one resource's text by name and by id ──────────────────
rd = C.tool_read_resource(project="Monolith Test", name="Roadmap")
ok("read_resource by fuzzy name returns the resource text",
   "Q3 roadmap" in (rd.get("text") or "") and rd.get("name") == "Roadmap.md", str(rd))
ok("read_resource flags resource text as untrusted owner data",
   rd.get("untrusted") is True and "instructions" in (rd.get("note") or "").lower())
rid = _by_name["Roadmap.md"]["id"]
ok("read_resource by resource_id returns the same resource",
   C.tool_read_resource(project=str(PID), resource_id=rid).get("resource_id") == rid)
binr = C.tool_read_resource(project="Monolith Test", name="diagram")
ok("read_resource on a binary resource returns metadata + note, no text",
   binr.get("text") is None and "no extracted text" in (binr.get("note") or ""), str(binr))
miss = C.tool_read_resource(project="Monolith Test", name="does-not-exist")
ok("read_resource on an unknown name errors and lists what IS available",
   miss.get("error") and "Roadmap.md" in (miss.get("available_resources") or []), str(miss))
ok("read_resource without a resource selector asks for one (no crash)",
   bool(C.tool_read_resource(project="Monolith Test").get("error")))

# ── B: search with no query falls back to the inventory instead of dead-ending ──────
sr = C.tool_search_project_resources(project="Monolith Test", query="")
ok("search_project_resources with empty query returns the inventory",
   sr.get("count") == 2 and "resources" in sr, str(sr))
sr2 = C.tool_search_project_resources(project="Monolith Test", query="roadmap")
ok("search_project_resources with a query still runs the RAG search",
   "results" in sr2 and sr2.get("query") == "roadmap", str(sr2))

# ── B/route: a project-read turn now advertises the resource read tools ─────────────
d = route_turn(TurnRequest(session_id="s", message="read resource from project Monolith 1, then report the roadmap",
                           mode="agent", model="x", capabilities={}), "STATUS")
ok("route_turn scopes a project-read turn to include read_resource + list_project_resources",
   "read_resource" in (d.allowed_tools or ()) and "list_project_resources" in (d.allowed_tools or ()),
   str(d.allowed_tools))

# ── A: an out-of-scope KNOWN read tool is admitted (not hard-denied) mid-turn ───────
from core import model_router as mr  # noqa: E402


class _Fake:
    def __init__(self, lines):
        self.lines = list(lines)

    def complete(self, messages, system=None, max_tokens=2000):
        return self.lines.pop(0) if self.lines else "Done, sir."


_orig_get_llm = mr.get_llm
# The model reaches for list_project_resources even though the (deliberately narrow) turn scope
# only authorized list_projects. Pre-fix: tool.route_denied → dead end. Post-fix: admitted + run.
mr.get_llm = lambda *a, **k: _Fake([
    '{"tool":"list_project_resources","args":{"project":"Monolith Test"}}',
    "Here are the resources, sir.",
])
try:
    res = C.answer("open project Monolith Test and show me what I uploaded", chat_id=-4242,
                   surface="mc", mode="agent", allowed_tools={"list_projects"})
finally:
    mr.get_llm = _orig_get_llm
ok("out-of-scope known read tool is admitted on demand (no route_denied dead-end)",
   "list_project_resources" in (res.get("tools_used") or []), str(res.get("tools_used")))

# ── A: a genuinely unknown tool still gets a recovery hint (names real tools), not surrender ──
_orig_read_doc = None
mr.get_llm = lambda *a, **k: _Fake([
    '{"tool":"read_resource_magic","args":{}}',       # hallucinated tool, not in READ_TOOLS
    '{"tool":"list_project_resources","args":{"project":"Monolith Test"}}',
    "Recovered, sir.",
])
try:
    res2 = C.answer("read the resource in project Monolith Test", chat_id=-4243,
                    surface="mc", mode="agent",
                    allowed_tools={"list_projects", "list_project_resources", "read_resource"})
finally:
    mr.get_llm = _orig_get_llm
ok("after an unknown-tool denial the model can still recover to a real read tool",
   "list_project_resources" in (res2.get("tools_used") or []), str(res2.get("tools_used")))

print(f"\n🎉 ALL {PASS} CHECKS PASSED")
