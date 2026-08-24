"""MCP Hub — M4: internet exposure via a cloudflared quick tunnel.

Spawns ``cloudflared tunnel --url http://localhost:<port>`` and captures the
public ``https://*.trycloudflare.com`` URL, persisting it to ``mcp_server_config``
and flipping ``exposed=1`` (which relaxes the Host allowlist on next start). Fully
graceful when cloudflared isn't installed.
"""
from __future__ import annotations

import os
import re
import shutil
import threading
import subprocess
from datetime import datetime, timezone

from core.database import get_connection
from core.proc import no_window

_URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")

_proc: subprocess.Popen | None = None
_public_url: str | None = None
_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def available() -> bool:
    return shutil.which("cloudflared") is not None


def _set_config(public_url: str | None, status: str, exposed: int | None = None) -> None:
    conn = get_connection()
    try:
        if exposed is None:
            conn.execute("UPDATE mcp_server_config SET public_url=?, tunnel_status=?, updated_at=? WHERE id=1",
                         (public_url, status, _now()))
        else:
            conn.execute("UPDATE mcp_server_config SET public_url=?, tunnel_status=?, exposed=?, updated_at=? WHERE id=1",
                         (public_url, status, exposed, _now()))
        conn.commit()
    finally:
        conn.close()


def status() -> dict:
    running = _proc is not None and _proc.poll() is None
    return {"available": available(), "running": running, "public_url": _public_url,
            "mcp_url": (f"{_public_url}/mcp" if _public_url else None)}


def start(port: int, timeout: float = 25.0) -> dict:
    """Start a quick tunnel and return the captured public URL (blocking up to timeout)."""
    global _proc, _public_url
    if not available():
        return {"ok": False, "error": "cloudflared is not installed. Install it and retry.",
                "hint": "https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/"}
    with _lock:
        if _proc is not None and _proc.poll() is None:
            return {"ok": True, "public_url": _public_url, "already_running": True}
        try:
            _proc = subprocess.Popen(
                ["cloudflared", "tunnel", "--url", f"http://localhost:{port}", "--no-autoupdate"],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
                creationflags=no_window(),
            )
        except Exception as e:
            return {"ok": False, "error": f"failed to launch cloudflared: {e}"}

    found = {"url": None}

    def _reader():
        assert _proc and _proc.stdout
        for line in _proc.stdout:
            m = _URL_RE.search(line)
            if m and not found["url"]:
                found["url"] = m.group(0)
                break

    t = threading.Thread(target=_reader, daemon=True)
    t.start()
    t.join(timeout)

    if not found["url"]:
        stop()
        return {"ok": False, "error": "tunnel did not produce a public URL in time"}
    _public_url = found["url"]
    _set_config(_public_url, "running", exposed=1)
    return {"ok": True, "public_url": _public_url, "mcp_url": f"{_public_url}/mcp",
            "note": "Restart the server to apply the relaxed Host allowlist for the tunnel."}


def stop() -> dict:
    global _proc, _public_url
    with _lock:
        if _proc is not None:
            try:
                _proc.terminate()
                try:
                    _proc.wait(timeout=5)
                except Exception:
                    _proc.kill()
            except Exception:
                pass
            _proc = None
        _public_url = None
    _set_config(None, "off", exposed=0)
    return {"ok": True, "running": False}
