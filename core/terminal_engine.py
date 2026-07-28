"""
TOBI TERMINAL ENGINE — queue #11 (the Agent-tier control base).

Upgrades the toy sandboxed ``run_bash`` (PROJECT_DIR-locked, 5-item denylist) in
``core/telegram_bot.py`` into a real, safe, **full-machine** execution engine that TOBI
uses to *do real things*: run commands, install/configure/connect tools — on request via
chat, Telegram, the REPL, and as Conductor (#7) chains.

Design (locked by the spec's 30 decisions, D1–D30):

**Two-axis safety (Codex-style) [D6].** Independent of each other:
  1. SCOPE [D7] — default = **full machine** (no PROJECT_DIR lock). The wide default is why
     the *safety floor* does the heavy lifting.
  2. APPROVAL MODE [D17] — **Plan / Ask (default) / Accept / Auto**, switchable anytime. The
     mode decides *when a command must ask*:

        | mode   | low | medium | high |
        |--------|-----|--------|------|
        | plan   |  —  |   —    |  —   |  (proposes only; executes nothing)
        | ask ⟵  | run | confirm| confirm |
        | accept | run |  run   | confirm |
        | auto   | run |  run   |  run |   (hard denylist still blocks)

**Hybrid risk classifier [D8].** Static rules for known-safe (→ low) and known-dangerous
(→ high / blocked); network-touching commands are auto-rated **medium** [D9]; commands that
touch TOBI's own repo/venv are forced **high** [D27]. Genuinely ambiguous commands default to
medium, and an optional Haiku judge can refine them.

**Safety floor [D25]** — the price of a full-machine default, all three:
  1. Absolute **hard denylist** (``rm -rf /``, disk wipes, fork bombs…) — *even Auto can't bypass*.
  2. Global **kill-switch** (``terminal.enabled``) — one flag freezes all execution.
  3. **Secret redaction** — mask API keys / tokens / vault values in output + audit.

**Background jobs [D11]** (``terminal_jobs``): long commands detach → id → inspect / kill later.
**Per-risk timeout [D12].** **Cross-platform [D26]** (PowerShell/cmd on Windows, bash/sh on POSIX).

This module is intentionally UI-agnostic: the Conductor exposes it as tools, the Chat page
streams it over SSE, Telegram summarises it, and the REPL drives it directly. Every execution
is audited to ``tobi_actions`` (#7) by the caller (the Conductor), so the blast radius here is
just *classify + gate + run*.
"""
from __future__ import annotations

import os
import re
import time
import shutil
import logging
import platform
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger("tobi.terminal")

REPO_ROOT = Path(__file__).resolve().parent.parent
IS_WINDOWS = os.name == "nt"

# ── Approval modes (Axis 2) ──────────────────────────────────────────────────────
MODES = ("plan", "ask", "accept", "auto")
DEFAULT_MODE = "ask"

# Timeout tiers (seconds) [D12] — background jobs are unbounded (None).
TIMEOUT_QUICK = 30
TIMEOUT_INSTALL = 300

# How much command output we keep (storage / model context).
OUTPUT_TAIL = 6000

# ════════════════════════════════════════════════════════════════════════════════
# Risk classification (hybrid) [D8]
# ════════════════════════════════════════════════════════════════════════════════
# 1) ABSOLUTE HARD DENYLIST — never runs, in ANY mode (supersedes _BLOCKED_CMDS) [D25].
#    Patterns are matched case-insensitively against the raw command line.
_HARD_DENY: list[tuple[str, str]] = [
    (r"\brm\s+-[a-z]*r[a-z]*f?\s+(/|~|\$HOME)(\s|$)", "recursive delete of a root/home path"),
    (r"\brm\s+-[a-z]*f[a-z]*r?\s+(/|~|\$HOME)(\s|$)", "recursive force-delete of a root/home path"),
    (r":\s*\(\s*\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:", "fork bomb"),
    (r"\bmkfs\.", "filesystem format (mkfs)"),
    (r"\bdd\b[^\n]*\bof=/dev/(sd|nvme|hd|disk)", "raw disk overwrite (dd to a block device)"),
    (r">\s*/dev/(sd|nvme|hd|disk)", "redirect over a block device"),
    (r"\bformat\s+[a-z]:", "Windows drive format"),
    (r"\bdel\b[^\n]*\s/[sq][^\n]*[a-z]:\\", "recursive Windows delete of a drive root"),
    (r"\brd\s+/s\b[^\n]*[a-z]:\\?\s*$", "recursive remove of a drive root (rd /s)"),
    (r"\bRemove-Item\b[^\n]*-Recurse[^\n]*\b[cC]:\\?\s*$", "recursive remove of C:\\ (PowerShell)"),
    (r"\bchmod\s+-R\s+0*7{3}\s+/(\s|$)", "chmod 777 -R on root"),
    (r"\b(shutdown|reboot|halt|poweroff)\b", "power state change (shutdown/reboot)"),
    (r"\bmkfs\b|\bfdisk\b|\bdiskpart\b", "partition / format tooling"),
    (r"\b(:(){|fork\s*bomb)\b", "fork bomb"),
]

# 2) KNOWN-DANGEROUS → high (propose+wait unless Auto) — destructive but sometimes legitimate.
_DANGER: list[tuple[str, str]] = [
    (r"\brm\s+-[a-z]*r", "recursive delete"),
    (r"\brmdir\s+/s", "recursive directory remove"),
    (r"\bRemove-Item\b[^\n]*-Recurse", "recursive remove (PowerShell)"),
    (r"\bdel\b[^\n]*\s/[sq]\b", "recursive/quiet delete"),
    (r"\bgit\s+(reset\s+--hard|clean\s+-[a-z]*f|push\s+--force|push\s+-f)", "destructive git operation"),
    (r"\b(kill|pkill|killall)\s+-9", "force-kill processes"),
    (r"\btaskkill\b[^\n]*/f", "force-kill (taskkill)"),
    (r"\bchmod\s+-R", "recursive permission change"),
    (r"\bchown\s+-R", "recursive ownership change"),
    (r"\btruncate\b", "truncate files"),
    (r">\s*/etc/", "overwrite a system config file"),
    (r"\bnpm\s+publish\b|\bpypi\b.*upload|\btwine\s+upload", "publish a package"),
    (r"\bDROP\s+(TABLE|DATABASE)\b", "drop a database object"),
]

# 3) NETWORK-TOUCHING → at least medium (act+report, logged) [D9]. Network is the exfil vector.
_NETWORK: list[tuple[str, str]] = [
    (r"\b(pip|pip3|pipx)\s+install\b", "pip install"),
    (r"\b(npm|pnpm|yarn)\s+(install|add|i)\b", "node package install"),
    (r"\bnpx\b", "npx (fetch + run)"),
    (r"\bwinget\s+(install|upgrade)\b", "winget install"),
    (r"\b(choco|scoop)\s+(install|upgrade)\b", "choco/scoop install"),
    (r"\b(apt|apt-get|dnf|yum|brew|pacman)\s+(install|upgrade|update)\b", "system package install"),
    (r"\bgit\s+(clone|pull|fetch|push)\b", "git network operation"),
    (r"\b(curl|wget|Invoke-WebRequest|iwr|Invoke-RestMethod)\b", "HTTP request"),
    (r"\bssh\b|\bscp\b|\brsync\b", "remote shell / copy"),
    (r"\bdocker\s+(pull|push|run)\b", "docker network operation"),
]

# 4) KNOWN-SAFE → low (auto). Read-only / inert inspection commands.
_SAFE: list[str] = [
    r"^\s*(ls|dir|pwd|cd|echo|cat|type|head|tail|less|more|wc|whoami|hostname|date|uptime)\b",
    r"^\s*(git\s+(status|log|diff|branch|show|remote|config\s+--get)|git\s+--version)\b",
    r"^\s*(pip|pip3|pipx)\s+(list|show|--version|freeze)\b",
    r"^\s*(npm|pnpm|yarn|node|npx)\s+(--version|-v|ls|list|view|outdated)\b",
    r"^\s*(python|python3|py)\s+(--version|-V)\b",
    r"^\s*(winget|choco|scoop)\s+(list|search|--version|-v)\b",
    r"^\s*(where|which|whereis|Get-Command|Get-ChildItem|Get-Location|Get-Process|gci|gcm|ls)\b",
    r"^\s*(printenv|env|set|Get-Content|Select-String|grep|rg|find|fd|tree)\b",
    r"^\s*(uname|systeminfo|df|du|free|Get-ComputerInfo)\b",
]

_SELF_REF_HINTS = ("terminal_engine", "conductor", "requirements.txt", "core/", "api/dashboard")


def _is_self_modify(command: str) -> bool:
    """A command that edits TOBI's own repo or pip-installs into its own venv [D27]."""
    low = command.lower()
    root = str(REPO_ROOT).lower().replace("\\", "/")
    norm = low.replace("\\", "/")
    if root and root in norm:
        # touching a path inside the repo, but only flag *write* verbs (reads are fine)
        if re.search(r"\b(rm|del|mv|move|cp|copy|>|>>|tee|Out-File|Set-Content|Add-Content|"
                     r"pip\s+install|pip\s+uninstall|git\s+(reset|checkout|clean|apply))\b", low):
            return True
    venv = str((REPO_ROOT / "venv")).lower().replace("\\", "/")
    if venv in norm and re.search(r"\b(pip|pip3|python)\b", low):
        return True
    if re.search(r"\bpip\s+(install|uninstall)\b", low) and any(h in norm for h in _SELF_REF_HINTS):
        return True
    return False


def classify_risk(command: str, use_llm: bool = False) -> tuple[str, str]:
    """Return (level, reason) where level ∈ {'low','medium','high','blocked'}.

    Rules decide the clear cases (fast, free); an optional Haiku judge only refines the
    ambiguous 'medium' default. Self-modification is always forced to high [D27]."""
    cmd = (command or "").strip()
    if not cmd:
        return "low", "empty command"

    for pat, why in _HARD_DENY:
        if re.search(pat, cmd, re.IGNORECASE):
            return "blocked", why

    if _is_self_modify(cmd):
        return "high", "touches TOBI's own repo/venv (self-modification)"

    for pat, why in _DANGER:
        if re.search(pat, cmd, re.IGNORECASE):
            return "high", why

    # network vs safe: a safe read wins only if it's ALSO not a network op
    net = next((why for pat, why in _NETWORK if re.search(pat, cmd, re.IGNORECASE)), None)
    if net:
        return "medium", net

    for pat in _SAFE:
        if re.search(pat, cmd, re.IGNORECASE):
            return "low", "known-safe inspection command"

    # Ambiguous → medium by default; optionally let a cheap judge refine.
    if use_llm:
        judged = _llm_judge(cmd)
        if judged:
            return judged
    return "medium", "unclassified — treating as medium (will confirm under Ask)"


def _llm_judge(command: str) -> Optional[tuple[str, str]]:
    """Haiku-tier judge for ambiguous commands [D8]. Best-effort; any failure → None (keep the
    rules-based default). Only ever returns low/medium/high — never 'blocked' (rules own that)."""
    try:
        from core.model_router import get_llm, restore_usage_context, set_usage_context
        prev = set_usage_context(
            "terminal", "risk_judge", purpose="safety_check",
            source="terminal", agent_id="tobi-terminal",
        )
        try:
            client = get_llm("simple")
            out = client.complete(
                [{"role": "user", "content":
                  f"Classify the RISK of running this shell command on the owner's machine. "
                  f"Reply with ONE word only: low, medium, or high.\nCommand: {command}"}],
                system="You are a security risk classifier. low = read-only/inert. "
                       "medium = writes files or touches the network. high = destructive or "
                       "irreversible. Answer with exactly one word.",
                max_tokens=8,
            )
        finally:
            restore_usage_context(prev)
        word = re.search(r"(low|medium|high)", (out or "").lower())
        if word:
            return word.group(1), "judged by the risk classifier"
    except Exception as e:  # noqa: BLE001
        logger.debug("risk judge skipped: %s", e)
    return None


# ════════════════════════════════════════════════════════════════════════════════
# Settings — approval mode + kill-switch (owner_settings key/value) [D17][D25]
# ════════════════════════════════════════════════════════════════════════════════
def _conn():
    from core.database import get_connection
    return get_connection()


def _get_setting(key: str, default: str) -> str:
    from core import owner_flags
    return owner_flags.get_str(key, default)


def _set_setting(key: str, value: str) -> None:
    from core import owner_flags
    owner_flags.set_str(key, value)


def get_mode() -> str:
    m = (_get_setting("terminal.mode", DEFAULT_MODE) or DEFAULT_MODE).lower()
    return m if m in MODES else DEFAULT_MODE


def set_mode(mode: str) -> str:
    mode = (mode or "").strip().lower()
    if mode not in MODES:
        raise ValueError(f"unknown mode '{mode}' (use plan|ask|accept|auto)")
    _set_setting("terminal.mode", mode)
    return mode


def is_enabled() -> bool:
    return _get_setting("terminal.enabled", "1") not in ("0", "false", "off", "no")


def set_enabled(enabled: bool) -> bool:
    _set_setting("terminal.enabled", "1" if enabled else "0")
    return enabled


def effective_mode(surface: str = "mc") -> str:
    """Telegram is capped at Ask [D18] — no Accept/Auto from the phone (no live console)."""
    mode = get_mode()
    if surface == "telegram" and mode in ("accept", "auto"):
        return "ask"
    return mode


# ════════════════════════════════════════════════════════════════════════════════
# Gate — compose scope × mode × risk into a decision [D6]
# ════════════════════════════════════════════════════════════════════════════════
_GATE_TABLE = {
    "ask":    {"low": "run", "medium": "confirm", "high": "confirm"},
    "accept": {"low": "run", "medium": "run", "high": "confirm"},
    "auto":   {"low": "run", "medium": "run", "high": "run"},
}


def gate(command: str, surface: str = "mc", use_llm: bool = True) -> dict:
    """Decide what to do with a command right now. Returns:
       {decision: 'run'|'confirm'|'plan'|'refuse', risk, reason, mode}."""
    if not is_enabled():
        return {"decision": "refuse", "risk": "blocked", "mode": get_mode(),
                "reason": "the terminal kill-switch is on — execution is frozen, sir"}
    level, reason = classify_risk(command, use_llm=use_llm)
    mode = effective_mode(surface)
    if level == "blocked":
        return {"decision": "refuse", "risk": "blocked", "mode": mode,
                "reason": f"hard safety denylist: {reason}"}
    if mode == "plan":
        return {"decision": "plan", "risk": level, "mode": mode, "reason": reason}
    decision = _GATE_TABLE[mode][level]
    return {"decision": decision, "risk": level, "mode": mode, "reason": reason}


# ════════════════════════════════════════════════════════════════════════════════
# Secret redaction [D25]
# ════════════════════════════════════════════════════════════════════════════════
_REDACT_PATTERNS = [
    re.compile(r"(?i)\b(api[_-]?key|token|secret|password|passwd|pwd|access[_-]?token|bearer)\b\s*[:=]\s*(\S+)"),
    re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"\bghp_[A-Za-z0-9]{20,}"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}"),
    re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"),  # JWT
]
_MASK = "‹redacted›"


def _vault_values() -> list[str]:
    """Best-effort: the actual secret VALUES currently injected into the environment, so any that
    surface in command output get masked. We only read env (never the vault ciphertext)."""
    out: list[str] = []
    try:
        for k, v in os.environ.items():
            if v and len(v) >= 12 and re.search(r"(?i)(key|token|secret|password|api)", k):
                out.append(v)
    except Exception:
        pass
    return out


def redact(text: str) -> str:
    if not text:
        return text
    red = text
    for val in _vault_values():
        if val in red:
            red = red.replace(val, _MASK)
    for pat in _REDACT_PATTERNS:
        if pat.groups >= 2:
            red = pat.sub(lambda m: m.group(0).replace(m.group(2), _MASK), red)
        else:
            red = pat.sub(_MASK, red)
    return red


# ════════════════════════════════════════════════════════════════════════════════
# Shell resolution (cross-platform) [D26]
# ════════════════════════════════════════════════════════════════════════════════
def _shell_argv(command: str) -> tuple[list[str], str]:
    """Return (argv, shell_name) for the current OS. Windows → PowerShell (fallback cmd);
    POSIX → bash (fallback sh)."""
    if IS_WINDOWS:
        ps = shutil.which("powershell") or shutil.which("pwsh")
        if ps:
            return [ps, "-NoProfile", "-NonInteractive", "-Command", command], "powershell"
        return ["cmd", "/c", command], "cmd"
    bash = shutil.which("bash")
    if bash:
        return [bash, "-lc", command], "bash"
    return ["sh", "-lc", command], "sh"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ════════════════════════════════════════════════════════════════════════════════
# Live-output sink — lets a surface (MC SSE) stream stdout without threading params
# through the Conductor's generic tool-call path.
# ════════════════════════════════════════════════════════════════════════════════
_OUTPUT_SINK: Optional[Callable[[str], None]] = None


def set_output_sink(fn: Optional[Callable[[str], None]]) -> Optional[Callable[[str], None]]:
    """Install a callback that receives each output chunk during run(); returns the previous one."""
    global _OUTPUT_SINK
    prev = _OUTPUT_SINK
    _OUTPUT_SINK = fn
    return prev


def _emit(chunk: str) -> None:
    if _OUTPUT_SINK and chunk:
        try:
            _OUTPUT_SINK(redact(chunk))
        except Exception:
            pass


# ════════════════════════════════════════════════════════════════════════════════
# Background-job registry [D11]
# ════════════════════════════════════════════════════════════════════════════════
def _ensure_jobs(conn) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS terminal_jobs (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            command    TEXT, cwd TEXT, shell TEXT,
            pid        INTEGER, status TEXT,                 -- running|done|failed|killed|timeout
            exit_code  INTEGER, output TEXT,
            risk       TEXT, mode TEXT, surface TEXT,
            started_at TEXT, ended_at TEXT
        )"""
    )


# live process handles keyed by job id (can't live in the DB)
_LIVE: dict[int, dict] = {}
_LIVE_LOCK = threading.Lock()


def _job_insert(command: str, cwd: str, shell: str, risk: str, mode: str, surface: str, pid: int) -> int:
    conn = _conn()
    try:
        _ensure_jobs(conn)
        cur = conn.execute(
            "INSERT INTO terminal_jobs (command, cwd, shell, pid, status, output, risk, mode, surface, started_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (command, cwd, shell, pid, "running", "", risk, mode, surface, _now()))
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def _job_finish(job_id: int, status: str, exit_code: Optional[int], output: str) -> None:
    conn = _conn()
    try:
        _ensure_jobs(conn)
        conn.execute(
            "UPDATE terminal_jobs SET status=?, exit_code=?, output=?, ended_at=? WHERE id=?",
            (status, exit_code, redact(output)[:OUTPUT_TAIL], _now(), job_id))
        conn.commit()
    finally:
        conn.close()


def _run_background(command: str, cwd: str, risk: str, mode: str, surface: str) -> dict:
    argv, shell = _shell_argv(command)
    proc = subprocess.Popen(argv, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, bufsize=1)
    job_id = _job_insert(command, cwd, shell, risk, mode, surface, proc.pid or 0)
    buf: list[str] = []
    with _LIVE_LOCK:
        _LIVE[job_id] = {"proc": proc, "buffer": buf}

    def _pump():
        try:
            if proc.stdout:
                for line in proc.stdout:
                    buf.append(line)
                    if len("".join(buf)) > OUTPUT_TAIL * 4:  # keep a bounded ring buffer
                        del buf[: len(buf) // 2]
            proc.wait()
        except Exception as e:  # noqa: BLE001
            buf.append(f"\n[job error: {e}]")
        finally:
            code = proc.returncode
            status = "done" if code == 0 else ("killed" if code is None else "failed")
            _job_finish(job_id, status, code, "".join(buf))
            with _LIVE_LOCK:
                _LIVE.pop(job_id, None)

    threading.Thread(target=_pump, daemon=True, name=f"tobi-job-{job_id}").start()
    return {"ok": True, "job_id": job_id, "background": True, "status": "running",
            "command": command, "cwd": cwd, "shell": shell, "risk": risk,
            "note": f"Started background job #{job_id}. Use list_jobs / kill_job to manage it, sir."}


def list_jobs(limit: int = 20) -> dict:
    conn = _conn()
    try:
        _ensure_jobs(conn)
        rows = conn.execute(
            "SELECT id, command, status, exit_code, cwd, risk, started_at, ended_at "
            "FROM terminal_jobs ORDER BY id DESC LIMIT ?", (max(1, min(limit, 100)),)).fetchall()
    finally:
        conn.close()
    jobs = []
    for r in rows:
        d = dict(r)
        # a live job reflects the in-memory tail; a finished one uses the stored output
        with _LIVE_LOCK:
            live = _LIVE.get(d["id"])
        d["live"] = bool(live)
        jobs.append(d)
    return {"count": len(jobs), "jobs": jobs}


def get_job(job_id: int, tail: int = OUTPUT_TAIL) -> dict:
    conn = _conn()
    try:
        _ensure_jobs(conn)
        row = conn.execute("SELECT * FROM terminal_jobs WHERE id=?", (int(job_id),)).fetchone()
    finally:
        conn.close()
    if not row:
        return {"error": f"no job #{job_id}"}
    d = dict(row)
    with _LIVE_LOCK:
        live = _LIVE.get(int(job_id))
    if live:
        d["output"] = redact("".join(live["buffer"]))[-tail:]
        d["live"] = True
    else:
        d["output"] = (d.get("output") or "")[-tail:]
        d["live"] = False
    return d


def kill_job(job_id: int) -> dict:
    with _LIVE_LOCK:
        live = _LIVE.get(int(job_id))
    if not live:
        return {"error": f"no running job #{job_id} (already finished?)"}
    proc = live["proc"]
    try:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
    except Exception as e:  # noqa: BLE001
        return {"error": f"couldn't kill job #{job_id}: {e}"}
    _job_finish(int(job_id), "killed", None, "".join(live["buffer"]))
    with _LIVE_LOCK:
        _LIVE.pop(int(job_id), None)
    return {"ok": True, "job_id": int(job_id), "status": "killed"}


# ════════════════════════════════════════════════════════════════════════════════
# Execute
# ════════════════════════════════════════════════════════════════════════════════
def _default_timeout(risk: str) -> int:
    return TIMEOUT_INSTALL if risk in ("medium", "high") else TIMEOUT_QUICK


def run(command: str, *, cwd: Optional[str] = None, timeout: Optional[int] = None,
        background: bool = False, risk: str = "low", mode: str = "ask",
        surface: str = "mc") -> dict:
    """Execute a command (already gated by the caller). Returns a compact result dict with the
    exit code + a redacted output tail, or a background job handle. Never raises."""
    command = (command or "").strip()
    if not command:
        return {"error": "empty command"}
    cwd = cwd or os.getcwd()
    if not os.path.isdir(cwd):
        cwd = os.getcwd()

    if background:
        try:
            return _run_background(command, cwd, risk, mode, surface)
        except Exception as e:  # noqa: BLE001
            return {"error": f"couldn't start background job: {e}"}

    argv, shell = _shell_argv(command)
    to = timeout if timeout is not None else _default_timeout(risk)
    t0 = time.time()
    try:
        proc = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=to)
        raw = ((proc.stdout or "") + (proc.stderr or "")).strip()
        out = redact(raw)
        _emit(out[-OUTPUT_TAIL:])
        truncated = len(out) > OUTPUT_TAIL
        return {
            "ok": proc.returncode == 0,
            "exit_code": proc.returncode,
            "output": out[-OUTPUT_TAIL:] if truncated else (out or "(no output)"),
            "truncated": truncated,
            "cwd": cwd, "shell": shell, "risk": risk, "mode": mode,
            "duration_ms": round((time.time() - t0) * 1000),
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "exit_code": None, "timed_out": True, "cwd": cwd, "shell": shell,
                "error": f"command timed out after {to}s", "risk": risk}
    except FileNotFoundError as e:
        return {"ok": False, "error": f"shell/command not found: {e}", "cwd": cwd, "risk": risk}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:300], "cwd": cwd, "risk": risk}


def plan(command: str, surface: str = "mc") -> dict:
    """Plan-mode preview: what running this command WOULD do — without executing it [D17]."""
    level, reason = classify_risk(command, use_llm=False)
    argv, shell = _shell_argv(command)
    return {
        "planned": True, "command": command, "risk": level, "reason": reason,
        "shell": shell, "cwd": os.getcwd(),
        "note": "Plan mode is on, sir — I'd run this but I'm holding off. Switch to Ask/Accept/Auto to execute.",
    }


# ════════════════════════════════════════════════════════════════════════════════
# Capability registry (installed_tools) [D15] + Hermes skills mirror
# ════════════════════════════════════════════════════════════════════════════════
def _ensure_tools(conn) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS installed_tools (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT UNIQUE,
            version     TEXT, channel TEXT,
            how_to_use  TEXT, wired INTEGER DEFAULT 0,
            status      TEXT DEFAULT 'installed',           -- installed|configured|connected|removed
            created_at  TEXT, updated_at TEXT
        )"""
    )


def register_tool(name: str, *, version: str = "", channel: str = "", how_to_use: str = "",
                  status: str = "installed") -> dict:
    name = (name or "").strip()
    if not name:
        return {"error": "name is required"}
    conn = _conn()
    try:
        _ensure_tools(conn)
        conn.execute(
            "INSERT INTO installed_tools (name, version, channel, how_to_use, status, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?) "
            "ON CONFLICT(name) DO UPDATE SET version=excluded.version, channel=excluded.channel, "
            "how_to_use=COALESCE(NULLIF(excluded.how_to_use,''), installed_tools.how_to_use), "
            "status=excluded.status, updated_at=excluded.updated_at",
            (name, version, channel, how_to_use, status, _now(), _now()))
        conn.commit()
    finally:
        conn.close()
    _mirror_skill(name, how_to_use, channel)
    return {"ok": True, "name": name, "status": status}


def list_tools() -> dict:
    conn = _conn()
    try:
        _ensure_tools(conn)
        rows = conn.execute(
            "SELECT name, version, channel, how_to_use, wired, status, updated_at "
            "FROM installed_tools WHERE status != 'removed' ORDER BY updated_at DESC").fetchall()
    finally:
        conn.close()
    return {"count": len(rows), "tools": [dict(r) for r in rows]}


def set_tool_wired(name: str, wired: bool = True) -> dict:
    conn = _conn()
    try:
        _ensure_tools(conn)
        conn.execute("UPDATE installed_tools SET wired=?, updated_at=? WHERE name=?",
                     (1 if wired else 0, _now(), name))
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "name": name, "wired": wired}


def _mirror_skill(name: str, how_to_use: str, channel: str) -> None:
    """Mirror an acquired tool into ~/.hermes/skills so the always-on runtime knows it too [D15].
    Best-effort — never raises."""
    try:
        skills_dir = Path(os.path.expanduser("~")) / ".hermes" / "skills"
        skills_dir.mkdir(parents=True, exist_ok=True)
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", name)[:60] or "tool"
        body = (f"# {name}\n\n"
                f"- Acquired via: {channel or 'terminal'}\n"
                f"- Registered by TOBI on {_now()}\n\n"
                f"## How to use\n\n{how_to_use or '(run `' + name + ' --help`)'}\n")
        (skills_dir / f"{safe}.md").write_text(body, encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        logger.debug("hermes skill mirror skipped: %s", e)


# ════════════════════════════════════════════════════════════════════════════════
# Acquire — build install commands for the supported package managers [D13]
# ════════════════════════════════════════════════════════════════════════════════
# manager → (availability check binary, install-command template)
_MANAGERS: dict[str, tuple[str, str]] = {
    "pip": ("pip", "pip install {pkg}"),
    "pipx": ("pipx", "pipx install {pkg}"),
    "npm": ("npm", "npm install -g {pkg}"),
    "pnpm": ("pnpm", "pnpm add -g {pkg}"),
    "winget": ("winget", "winget install --silent --accept-package-agreements --accept-source-agreements {pkg}"),
    "choco": ("choco", "choco install -y {pkg}"),
    "scoop": ("scoop", "scoop install {pkg}"),
}


def available_managers() -> list[str]:
    return [m for m, (binary, _) in _MANAGERS.items() if shutil.which(binary)]


def install_command(manager: str, package: str) -> Optional[str]:
    spec = _MANAGERS.get((manager or "").lower())
    if not spec:
        return None
    # basic shell-injection guard on the package token
    pkg = (package or "").strip()
    if not pkg or re.search(r"[;&|`$><\n]", pkg):
        return None
    return spec[1].format(pkg=pkg)


def resolve_manager(manager: str = "") -> Optional[str]:
    """Pick the manager to use: the requested one if present, else the first available."""
    manager = (manager or "").strip().lower()
    avail = available_managers()
    if manager and manager in _MANAGERS:
        return manager if manager in avail else None
    return avail[0] if avail else None


# ════════════════════════════════════════════════════════════════════════════════
# Introspection (status card)
# ════════════════════════════════════════════════════════════════════════════════
def status() -> dict:
    return {
        "enabled": is_enabled(),
        "mode": get_mode(),
        "os": platform.system(),
        "shell": _shell_argv("echo")[1],
        "cwd": os.getcwd(),
        "package_managers": available_managers(),
        "tools_registered": list_tools()["count"],
        "modes": list(MODES),
    }
