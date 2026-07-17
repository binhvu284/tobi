"""Repository-backed architecture diagrams (queue #20, Architecture V2).

Reads the canonical Mermaid flowcharts under ``docs/architecture/diagrams/`` and their guide
sidecars, validates them against a strict flowchart-only policy (the same policy the runtime and
the tests enforce), and exposes read-only Git history for each. Structured like
``core/hermes_skills.py``: a fixed directory + an enum allowlist, never a client-supplied path;
**never raises** — every failure degrades to empty/None/``valid: False`` so a route can't 500 and
an invalid diagram is never returned for rendering.

Security posture:
- Only the two allowlisted diagram ids resolve to a file; arbitrary ids/paths return None.
- The validator is allow-list first (flowchart subset, per-line classification, anything
  unclassified rejected) with a banned-token deny-list as defense in depth. It bans ``<`` (raw
  HTML / ``<br/>``), ``%%{`` directives, ``click``/``href``/JS/data URLs, and style/class hooks.
- Git version reads allowlist the FULL 40-hex commit SHA against ``git log`` for that exact file
  before ``git show``; list-argv (no shell) blocks option/argv injection.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

# <repo>/core/architecture_docs.py  ->  <repo>
_ROOT = Path(__file__).resolve().parent.parent
DIAGRAMS_DIR = _ROOT / "docs" / "architecture" / "diagrams"

# Enum allowlist — the ONLY ids that resolve to a file (cf. api/dashboard.py ALLOWED_* sets).
DIAGRAMS: dict[str, dict] = {
    "overall-tobi": {
        "title": "Overall TOBI", "file": "overall-tobi.mmd", "guide": "overall-tobi.guide.md",
        "description": "How the whole TOBI service fits together across surfaces, engines, and data.",
    },
    "mission-control": {
        "title": "Mission Control", "file": "mission-control.mmd", "guide": "mission-control.guide.md",
        "description": "The React Mission Control frontend: providers, shell, panes, and the API client.",
    },
}

MAX_DIAGRAM_BYTES = 64 * 1024
MAX_LINES = 400
MAX_NODES = 120
MAX_LABEL = 120

# ── validator ───────────────────────────────────────────────────────────────────────
_ALLOWED_HEADER = re.compile(r"^flowchart\s+(TD|TB|LR|RL|BT)$")
# Banned anywhere (case-insensitive), as defense in depth over the structural allow-list.
_BANNED = ("<", "%%{", "click ", "href", "javascript:", "data:", "vbscript:", "call ",
           "linkstyle", "classdef", "class ", "_blank", "script", "style ", "@import")

_ID = r"[A-Za-z0-9_]+"
_SHAPE = (r"(?:\[\([^\]]*\)\]"    # [(cylinder)]
          r"|\(\([^)]*\)\)"      # ((circle))
          r"|\{[^}]*\}"          # {rhombus}
          r"|\[[^\]]*\]"         # [rectangle]
          r"|\([^)]*\))")        # (rounded)
_NODEREF = rf"{_ID}\s*(?:{_SHAPE})?"
_ARROW = r"(?:-->|---|-\.->|-\.-|==>|===|--o|--x|o--o|x--x)"
_EDGE = re.compile(rf"^{_NODEREF}(?:\s*{_ARROW}\s*(?:\|[^|]*\|\s*)?{_NODEREF})+$")
_NODE = re.compile(rf"^{_NODEREF}$")
_SUBGRAPH = re.compile(rf'^subgraph\s+(?:{_ID}|"[^"]*")(?:\s*\[[^\]]*\])?$')
_END = re.compile(r"^end$")
_LABELS = re.compile(r"\[\(([^\]]*)\)\]|\[([^\]]*)\]|\(([^)]*)\)|\{([^}]*)\}")
_DEFS = re.compile(rf"({_ID})\s*(?:{_SHAPE})")


def validate(text: str) -> tuple[bool, list[str]]:
    """Return (ok, reasons). Fail closed: any doubt → (False, [...]). Never raises."""
    try:
        raw = text or ""
        if len(raw.encode("utf-8", "replace")) > MAX_DIAGRAM_BYTES:
            return False, ["diagram exceeds the size limit"]
        low = raw.lower()
        for bad in _BANNED:
            if bad in low:
                return False, [f"banned token present: {bad.strip() or bad!r}"]
        lines = raw.splitlines()
        if len(lines) > MAX_LINES:
            return False, ["too many lines"]
        header_seen = False
        node_ids: set[str] = set()
        for ln in (s.strip() for s in lines):
            if not ln or ln.startswith("%%"):
                continue
            if not header_seen:
                if not _ALLOWED_HEADER.match(ln):
                    return False, [f"first directive must be 'flowchart <DIR>', got {ln[:40]!r}"]
                header_seen = True
                continue
            if _END.match(ln) or _SUBGRAPH.match(ln):
                continue
            if _EDGE.match(ln) or _NODE.match(ln):
                for groups in _LABELS.findall(ln):
                    if any(len(g) > MAX_LABEL for g in groups):
                        return False, ["a node label exceeds the length limit"]
                node_ids.update(_DEFS.findall(ln))
                continue
            return False, [f"unclassified line: {ln[:60]!r}"]
        if not header_seen:
            return False, ["missing flowchart header"]
        if len(node_ids) > MAX_NODES:
            return False, ["too many nodes"]
        return True, []
    except Exception as exc:  # never raise out of the validator
        return False, [f"validator error: {str(exc)[:80]}"]


# ── read ─────────────────────────────────────────────────────────────────────────────
def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
    except Exception:
        return ""


def list_diagrams() -> dict:
    items = [{"id": k, "title": v["title"], "description": v["description"]} for k, v in DIAGRAMS.items()]
    return {"items": items, "count": len(items)}


def get_diagram(diagram_id: str):
    """Full diagram: validated Mermaid content + guide markdown. Unknown id → None. Invalid
    content → valid:False with empty content (never hand back unsafe Mermaid to render)."""
    meta = DIAGRAMS.get(diagram_id)
    if not meta:
        return None
    content = _read(DIAGRAMS_DIR / meta["file"])
    ok, reasons = validate(content)
    if not ok:
        return {"id": diagram_id, "title": meta["title"], "description": meta["description"],
                "content": "", "guide": "", "valid": False, "reasons": reasons}
    return {"id": diagram_id, "title": meta["title"], "description": meta["description"],
            "content": content, "guide": _read(DIAGRAMS_DIR / meta["guide"]), "valid": True, "reasons": []}


# ── git-backed version history (soft-failing; never raises, never 500s) ────────────────
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def _git(*args: str):
    try:
        out = subprocess.run(["git", *args], cwd=str(_ROOT), capture_output=True, text=True, timeout=6)
        return out.stdout if out.returncode == 0 else None
    except Exception:
        return None


def history(diagram_id: str, limit: int = 10):
    """Recent commits that touched this diagram's file. Unknown id → None. Not a git checkout →
    {available: False}. SHAs returned as full %H (allowlist key) + short (display)."""
    meta = DIAGRAMS.get(diagram_id)
    if not meta:
        return None
    try:
        n = max(1, min(int(limit), 20))
    except Exception:
        n = 10
    rel = f"docs/architecture/diagrams/{meta['file']}"  # from the enum, never client input
    out = _git("log", f"--max-count={n}", "--format=%H%x1f%h%x1f%aI%x1f%s", "--", rel)
    if out is None:
        return {"items": [], "count": 0, "available": False}
    items = []
    for line in out.splitlines():
        parts = line.split("\x1f")
        if len(parts) == 4 and _SHA_RE.match(parts[0]):
            items.append({"sha": parts[0], "short": parts[1], "date": parts[2], "subject": parts[3][:200]})
    return {"items": items, "count": len(items), "available": True}


def version(diagram_id: str, sha: str):
    """A historical version's validated content. The sha must be a full 40-hex commit that is a
    member of this diagram's own history() — never interpolate a raw client ref into git."""
    meta = DIAGRAMS.get(diagram_id)
    if not meta:
        return None
    if not isinstance(sha, str) or not _SHA_RE.match(sha):
        return None
    hist = history(diagram_id, 20)
    if not hist or not hist.get("available") or sha not in {it["sha"] for it in hist["items"]}:
        return None
    text = _git("show", f"{sha}:docs/architecture/diagrams/{meta['file']}")
    if text is None:
        return None
    ok, _reasons = validate(text)
    if not ok:
        return None
    return {"id": diagram_id, "sha": sha, "short": sha[:8], "content": text, "valid": True}


# ── layer prose (moved verbatim from conductor._ARCHITECTURE; #20 collapses a drift source) ──
LAYERS = {
    "summary": "TOBI is a personal-Jarvis agent: a Python service that runs Mission Control "
               "and a Telegram bot over one shared brain.",
    "layers": [
        {"layer": "Host / runtime", "detail": "Python 3 process on a Windows dev box (local migration) or VPS; "
         "main.py is the orchestrator + scheduler (run modes: start/bot/api/research/execute/ceo)."},
        {"layer": "API", "detail": "FastAPI in api/dashboard.py serves the Mission Control dashboard and every "
         "/api/* endpoint, plus the mounted MCP server."},
        {"layer": "Engines (core/)", "detail": "model_router, task_classifier, research, executor, CEO loop, "
         "brain (the second brain), graph_engine, and this conductor."},
        {"layer": "Data", "detail": "SQLite (core/database.py): projects, tasks, agents, missions, lessons, "
         "conversations, brain_memories, and the encrypted vault."},
        {"layer": "Interfaces", "detail": "The React Mission Control chat and the Telegram bot — both front doors "
         "onto the Conductor."},
        {"layer": "Integrations", "detail": "The Genesis vault holds encrypted credentials for Notion, GitHub, "
         "Vercel, Supabase, Telegram, the LLM providers, and Tavily."},
    ],
}


def layers() -> dict:
    """The layer-by-layer prose the Conductor's explain_architecture tool grounds on."""
    return LAYERS
