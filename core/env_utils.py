"""Environment loading helpers.

Keeps startup resilient when python-dotenv is not installed, and forces stdout/stderr
to UTF-8 so emoji / box-drawing characters in log lines can't crash the process on a
non-UTF-8 Windows console (e.g. Vietnamese cp1258). Tobi is developed on Linux but now
also runs on local Windows, where `print("✅ …")` otherwise raises UnicodeEncodeError.
"""
import sys


def force_utf8_stdio() -> None:
    """Reconfigure stdout/stderr to UTF-8 (unencodable chars replaced) so Unicode prints
    never raise UnicodeEncodeError on a legacy console codepage. Idempotent, best-effort."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # py3.7+ text streams
        except Exception:
            pass  # stream already replaced/captured (e.g. pytest) — nothing to harden


def safe_load_dotenv() -> None:
    force_utf8_stdio()  # harden console encoding before any startup banner/emoji is printed
    try:
        from dotenv import load_dotenv  # type: ignore
    except Exception:
        return
    load_dotenv()
