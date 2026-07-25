"""Conductor terminal tools — #11 CLI status + run/install/configure/connect/kill.

Extracted from core/conductor.py (Phase 2 — pre-#21 decomposition). Verbatim move;
behavior identical. core.terminal_engine et al. are imported inline inside each tool.
The read tools register into READ_TOOLS; the act tools into ACT_TOOLS (conductor.py).
"""
from __future__ import annotations

import os  # noqa: F401 - used by some tools
from typing import Any  # noqa: F401 - used in signatures
def tool_terminal_status(**_: Any) -> dict:
    """Terminal engine status: approval mode, kill-switch, OS/shell, package managers, tools [D22]."""
    from core import terminal_engine as te
    return te.status()


def tool_list_jobs(**_: Any) -> dict:
    """Background terminal jobs: id, command, status, exit code [D11]."""
    from core import terminal_engine as te
    return te.list_jobs()


def tool_job_output(job_id: int = 0, **_: Any) -> dict:
    """The output (and status) of one background terminal job. Arg: job_id (int)."""
    from core import terminal_engine as te
    try:
        return te.get_job(int(job_id))
    except Exception as e:
        return {"error": str(e)[:200]}


def tool_list_installed_tools(**_: Any) -> dict:
    """TOBI's capability registry: tools it has installed/configured/connected [D15]."""
    from core import terminal_engine as te
    return te.list_tools()


def tool_run_command(command: str = "", cwd: str = "", background: bool = False,
                     timeout: int = 0, **_: Any) -> dict:
    """Run a shell command on the machine (gating already decided by the engine)."""
    from core import terminal_engine as te
    command = (command or "").strip()
    if not command:
        return {"error": "command is required"}
    try:
        risk = te.classify_risk(command)[0]
    except Exception:
        risk = "medium"
    try:
        timeout = int(timeout) or None
    except Exception:
        timeout = None
    return te.run(command, cwd=(cwd or None), background=bool(background), timeout=timeout, risk=risk)


def tool_install_package(package: str = "", manager: str = "", **_: Any) -> dict:
    """Install a package via pip/pipx/npm/pnpm/winget/choco/scoop, then register it [D13][D15]."""
    from core import terminal_engine as te
    package = (package or "").strip()
    if not package:
        return {"error": "package is required"}
    mgr = te.resolve_manager(manager)
    if not mgr:
        avail = te.available_managers()
        return {"error": "no usable package manager" + (f" — available here: {', '.join(avail)}" if avail
                         else " found on this machine")}
    cmd = te.install_command(mgr, package)
    if not cmd:
        return {"error": f"couldn't build a safe install command for '{package}' via {mgr}"}
    res = te.run(cmd, risk="medium", timeout=te.TIMEOUT_INSTALL)
    if res.get("ok"):
        try:
            te.register_tool(package, channel=mgr, status="installed",
                             how_to_use=f"Installed via {mgr}. Try `{package} --help`.")
            res["registered"] = True
            res["wire_offer"] = (f"'{package}' is installed and in your toolset, sir — want me to wire it as a "
                                 "reusable tool so future calls skip raw shell?")
        except Exception:
            pass
    return res


def tool_configure_tool(name: str = "", path: str = "", content: str = "", append: bool = False, **_: Any) -> dict:
    """Configure an acquired tool by writing/appending its config file [D14]."""
    from core import terminal_engine as te
    path = (path or "").strip()
    if not path:
        return {"error": "path is required"}
    p = os.path.expanduser(path)
    try:
        parent = os.path.dirname(p)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(p, "a" if append else "w", encoding="utf-8") as f:
            f.write(content or "")
    except Exception as e:
        return {"error": str(e)[:200]}
    if (name or "").strip():
        try:
            te.register_tool(name.strip(), status="configured", how_to_use=f"Configured at {p}")
        except Exception:
            pass
    return {"ok": True, "name": name or path, "path": p, "bytes": len(content or ""), "appended": bool(append)}


def tool_connect_tool(name: str = "", secret_name: str = "", login_command: str = "", **_: Any) -> dict:
    """Connect an acquired tool: reference an EXISTING vault/env credential (never a plaintext
    secret through chat) and optionally run the tool's login/setup command [D14]."""
    from core import terminal_engine as te
    name = (name or "").strip()
    if not name:
        return {"error": "name is required"}
    secret_name = (secret_name or "").strip()
    cred_ok = None
    if secret_name:
        cred_ok = bool(os.getenv(secret_name))
        if not cred_ok:
            try:
                from core import vault
                from core.database import get_connection
                conn = get_connection()
                try:
                    cred_ok = any(s.get("name") == secret_name for s in vault.list_secrets(conn))
                finally:
                    conn.close()
            except Exception:
                cred_ok = False
        if not cred_ok:
            return {"error": f"no credential named '{secret_name}' is stored yet, sir — add it in Integrations "
                             "(the Genesis vault) first, then I'll connect the tool."}
    out: dict = {"ok": True, "name": name, "credential": secret_name or None, "credential_found": cred_ok}
    login_command = (login_command or "").strip()
    if login_command:
        risk = te.classify_risk(login_command)[0]
        out["login"] = te.run(login_command, risk=risk)
    try:
        te.register_tool(name, status="connected",
                         how_to_use=(f"Connected (credential '{secret_name}' in vault)." if secret_name else "Connected."))
    except Exception:
        pass
    return out


def tool_kill_job(job_id: int = 0, **_: Any) -> dict:
    """Stop a running background terminal job [D11]."""
    from core import terminal_engine as te
    try:
        return te.kill_job(int(job_id))
    except Exception as e:
        return {"error": str(e)[:200]}


def tool_set_terminal_mode(mode: str = "", **_: Any) -> dict:
    """Switch the terminal approval mode: plan | ask | accept | auto [D17]."""
    from core import terminal_engine as te
    try:
        m = te.set_mode(mode)
    except Exception as e:
        return {"error": str(e)[:120]}
    return {"ok": True, "mode": m}
