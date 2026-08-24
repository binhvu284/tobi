"""Starting a child process must never take over the owner's screen.

TOBI runs as a background server. When it shells out — to `git`, to `tasklist`, to a test suite,
to a worker — Windows gives the child a console. If the server has no console of its own to lend
it, the child gets a **new** one: a black window that appears, flashes, and vanishes.

The owner hit this on 2026-08-21 pressing the Infrastructure test button, which starts 23 child
processes in a row. It was never only cosmetic: a window that takes focus for a moment can eat a
keystroke, and it makes a background tool look like it is doing something it should not be.
Twenty call sites did this, one flash at a time, long before the button made it obvious.

`CREATE_NO_WINDOW` prevents it and costs nothing when the parent does have a console. The flag
exists only on Windows, so this is a no-op everywhere else.

Pass `creationflags=no_window()` to every `subprocess.run`/`Popen` the server can reach, and
`no_window(FLAG)` where the call already needs flags of its own.
`tests/test_no_console_windows.py` fails if a call site forgets.
"""
from __future__ import annotations

import os
import subprocess

# `getattr` because the constant does not exist off Windows, and 0 is the neutral value for a
# flags field, so callers never need their own platform check.
CREATE_NO_WINDOW: int = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


def no_window(extra: int = 0) -> int:
    """Creation flags that suppress a new console window, keeping any flags the caller needs."""
    return int(extra) | CREATE_NO_WINDOW
