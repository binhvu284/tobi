"""
ARCHITECTURE DOCS (queue #20 Phase B) — canonical diagrams, fail-closed validator, SHA allowlist.

Plain python, no DB needed (read-only repo module):
    python tests/test_architecture_docs.py

Covers: the two canonical files pass the runtime validator (= the CI gate); every unsafe-Mermaid
vector is rejected; the enum allowlist blocks unknown/traversal ids; the git version reader
allowlists a full 40-hex sha against the file's own history (rejecting short/injection/option
shas) and fails closed; non-git checkout degrades to available:false; and every source path named
in the moved LAYERS prose resolves on disk (drift guard).
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from core import architecture_docs as AD  # noqa: E402

PASS = 0


def ok(name: str, cond: bool, detail: str = ""):
    global PASS
    if not cond:
        print(f"❌ {name} {detail}")
        sys.exit(1)
    PASS += 1
    print(f"✅ {name}")


# ── list + canonical files pass the runtime validator (the CI gate) ─────────────────
lst = AD.list_diagrams()
# Counted from the allowlist rather than pinned to a number: a new diagram is a normal
# change, but one that is registered and missing from disk is not.
ok("list_diagrams returns {items,count} covering every registered diagram",
   lst["count"] == len(AD.DIAGRAMS) and len(lst["items"]) == len(AD.DIAGRAMS), str(lst))
ok("every registered diagram has its file and guide on disk",
   all((AD.DIAGRAMS_DIR / spec["file"]).is_file() and (AD.DIAGRAMS_DIR / spec["guide"]).is_file()
       for spec in AD.DIAGRAMS.values()),
   str([spec["file"] for spec in AD.DIAGRAMS.values()
        if not (AD.DIAGRAMS_DIR / spec["file"]).is_file()]))
ok("every registered diagram passes the validator",
   all(AD.validate((AD.DIAGRAMS_DIR / spec["file"]).read_text(encoding="utf-8"))[0]
       for spec in AD.DIAGRAMS.values()),
   str([name for name, spec in AD.DIAGRAMS.items()
        if not AD.validate((AD.DIAGRAMS_DIR / spec["file"]).read_text(encoding="utf-8"))[0]]))
for did in ("overall-tobi", "mission-control"):
    d = AD.get_diagram(did)
    ok(f"canonical '{did}' validates and has content", d is not None and d["valid"] and len(d["content"]) > 50, str(d and d.get("reasons")))
    ok(f"canonical '{did}' ships a guide", bool(d["guide"]) and "##" in d["guide"])

# ── enum allowlist: unknown / traversal ids → None ──────────────────────────────────
ok("unknown diagram id → None", AD.get_diagram("nope") is None)
ok("path-traversal id → None", AD.get_diagram("../../../etc/passwd") is None)
ok("history unknown id → None", AD.history("nope") is None)
ok("version unknown id → None", AD.version("nope", "0" * 40) is None)

# ── the validator rejects every unsafe vector (one check each) ───────────────────────
_H = "flowchart TD\n"
vectors = {
    "%%{init}%% directive": _H + "%%{init: {'theme':'x'}}%%\nA-->B",
    "graph TD header": "graph TD\nA-->B",
    "sequenceDiagram": "sequenceDiagram\nA->>B: hi",
    "gantt": "gantt\ntitle x",
    "click handler": _H + "A-->B\nclick A callback",
    "click http link": _H + "A-->B\nclick A \"http://evil\"",
    "raw html label": _H + "A[<img src=x onerror=alert(1)>]-->B",
    "<br/> in label": _H + "A[line<br/>break]-->B",
    "href": _H + "A-->B\nA href \"http://x\"",
    "javascript url": _H + "A-->B\nclick A javascript:alert(1)",
    "data url": _H + "A[data:text/html,x]-->B",
    "classDef": _H + "A-->B\nclassDef big fill:#f00",
    "style directive": _H + "A-->B\nstyle A fill:#f00",
    "linkStyle": _H + "A-->B\nlinkStyle 0 stroke:#f00",
    "empty": "",
    "no header": "A-->B\nC-->D",
    "unclassified junk": _H + "A-->B\nDROP TABLE users;",
    "too many lines": _H + "\n".join(f"A-->N{i}" for i in range(500)),
    "oversize label": _H + "A[" + ("x" * 200) + "]-->B",
}
for name, txt in vectors.items():
    valid, reasons = AD.validate(txt)
    ok(f"reject: {name}", valid is False, "unexpectedly accepted")

# ── the validator ACCEPTS legitimate flowchart shapes ───────────────────────────────
ok("accept: rect + cylinder + arrow", AD.validate("flowchart LR\nA[Hello world]-->B[(SQLite)]")[0] is True)
ok("accept: dotted edge + edge label", AD.validate("flowchart TD\nA-->|does thing|B\nB-.->C")[0] is True)
ok("accept: subgraph/end", AD.validate("flowchart TD\nsubgraph S\nA-->B\nend")[0] is True)

# ── git SHA allowlist: reject short/injection/option shas; fail closed ───────────────
ok("version rejects a non-hex sha", AD.version("overall-tobi", "not-a-sha") is None)
ok("version rejects a 7-char short sha", AD.version("overall-tobi", "de0de0d") is None)
ok("version rejects an argv-injection sha", AD.version("overall-tobi", "-x") is None)
ok("version rejects a shell-injection sha", AD.version("overall-tobi", "'; rm -rf /") is None)
ok("version rejects a 40-hex sha NOT in this file's history", AD.version("overall-tobi", "d" * 40) is None)

# ── deterministic git behavior via monkeypatched _git ───────────────────────────────
_real_git = AD._git
_FAKE_SHA = "a" * 40
try:
    def _fake_git(*args):
        if args[:1] == ("log",):
            return f"{_FAKE_SHA}\x1faaaaaaaa\x1f2026-07-16T00:00:00Z\x1fseed diagrams\n"
        if args[:1] == ("show",):
            return "flowchart TD\n  A[Old]-->B[Version]\n"
        return None
    AD._git = _fake_git
    h = AD.history("overall-tobi", 5)
    ok("history reports available with a full-40 sha + short", h["available"] and h["items"][0]["sha"] == _FAKE_SHA and h["items"][0]["short"] == "aaaaaaaa")
    v = AD.version("overall-tobi", _FAKE_SHA)
    ok("version returns validated content for an allowlisted sha", v is not None and v["valid"] and "Version" in v["content"])
    # a valid-hex sha that isn't the one history returns is still rejected
    ok("version rejects an allowlisted-shape sha absent from history", AD.version("overall-tobi", "b" * 40) is None)

    def _git_show_bad(*args):
        if args[:1] == ("log",):
            return f"{_FAKE_SHA}\x1faaaaaaaa\x1f2026-07-16T00:00:00Z\x1fx\n"
        if args[:1] == ("show",):
            return "sequenceDiagram\nA->>B: sneaky"  # historical content that fails validation
        return None
    AD._git = _git_show_bad
    ok("version fails closed when a historical version is unsafe", AD.version("overall-tobi", _FAKE_SHA) is None)

    AD._git = lambda *a: None  # simulate a non-git checkout
    ok("history on a non-git checkout → available:false, no raise", AD.history("overall-tobi")["available"] is False)
    ok("version on a non-git checkout → None", AD.version("overall-tobi", _FAKE_SHA) is None)
finally:
    AD._git = _real_git

# ── LAYERS drift guard: every source path in the prose resolves on disk ──────────────
_root = AD._ROOT
_paths = set()
for layer in AD.LAYERS["layers"]:
    for tok in re.findall(r"[A-Za-z0-9_./]+\.py", layer["detail"]):
        _paths.add(tok)
ok("LAYERS names at least a few real files", len(_paths) >= 2, str(_paths))
for p in sorted(_paths):
    ok(f"LAYERS path exists: {p}", (_root / p).exists())

print(f"\n🎉 ALL {PASS} CHECKS PASSED")
