"""Runtime build identity used by deployment health verification."""
from __future__ import annotations

import os
import subprocess
from functools import lru_cache
from pathlib import Path
from core.proc import no_window


@lru_cache(maxsize=1)
def revision() -> str:
    declared = os.getenv("TOBI_DEPLOY_REVISION", "").strip()
    if declared:
        return declared
    root = Path(__file__).resolve().parents[1]
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5,
            creationflags=no_window(),
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return "unknown"
