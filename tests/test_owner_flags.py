"""
OWNER FLAGS (queue #20, Step 0) — shared owner_settings helper + additive table repair.

Isolated temp DB (DB_PATH env), plain python, no pytest:
    DB_PATH=/tmp/tof.db python tests/test_owner_flags.py

Covers: canonical wide schema; the red->green updated_at repair of a bespoke narrow table
(reproducing the live PATCH /api/owner/settings 500); office-shaped NOT NULL legacy table;
bool/enum round-trips and fail-open reads; a behavior-parity table pinning every migrated
flag's no-row default (incl. chat_runtime_v2 fail-open); the new brain/architecture flags
default off; and vault's active-slot round-trip through the shared ensure_schema.
"""
import os
import sqlite3
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix="tobi_tof_")
os.environ["DB_PATH"] = os.path.join(_TMP, "agent.db")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from core.database import init_database, get_connection  # noqa: E402

init_database()

from core import owner_flags as OF  # noqa: E402

PASS = 0


def ok(name: str, cond: bool, detail: str = ""):
    global PASS
    if not cond:
        print(f"❌ {name} {detail}")
        sys.exit(1)
    PASS += 1
    print(f"✅ {name}")


def _cols(conn) -> list:
    return [r[1] for r in conn.execute("PRAGMA table_info(owner_settings)")]


# ── canonical wide schema on a fresh DB ─────────────────────────────────────────────
conn = get_connection()
ok("fresh DB has the wide canonical shape", _cols(conn) == ["key", "value", "updated_at"], str(_cols(conn)))
conn.close()

# ── THE repair test: a bespoke narrow table → wide upsert 500 → ensure_schema → green ─
_p = os.path.join(_TMP, "narrow.db")
raw = sqlite3.connect(_p)
raw.execute("CREATE TABLE owner_settings (key TEXT PRIMARY KEY, value TEXT)")  # bespoke narrow
raw.commit()
_wide_upsert = ("INSERT INTO owner_settings (key, value, updated_at) VALUES ('k','v',CURRENT_TIMESTAMP) "
               "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP")
_raised = False
try:
    raw.execute(_wide_upsert)
except sqlite3.OperationalError:
    _raised = True
ok("narrow table rejects the updated_at upsert (reproduces the live 500)", _raised)
OF.ensure_schema(raw)  # additive repair
ok("updated_at added by ensure_schema", "updated_at" in _cols(raw))
raw.execute(_wide_upsert)  # now succeeds
raw.commit()
ok("after repair, the wide upsert succeeds", raw.execute("SELECT value FROM owner_settings WHERE key='k'").fetchone()[0] == "v")
raw.close()

# ── office-shaped legacy table (value TEXT NOT NULL) survives repair + round-trip ────
_p2 = os.path.join(_TMP, "office.db")
raw2 = sqlite3.connect(_p2)
raw2.execute("CREATE TABLE owner_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
raw2.commit()
OF.ensure_schema(raw2)
raw2.execute(_wide_upsert)
raw2.commit()
ok("NOT NULL legacy table survives repair + round-trip", "updated_at" in _cols(raw2))
raw2.close()

# ── bool round-trips + unrecognized → default ───────────────────────────────────────
for token, expect in (("1", True), ("true", True), ("on", True), ("yes", True),
                      ("0", False), ("false", False), ("off", False), ("no", False)):
    OF.set_str("t.bool", token)
    ok(f"get_bool reads {token!r} as {expect}", OF.get_bool("t.bool", not expect) is expect)
OF.set_str("t.bool", "maybe")
ok("get_bool unrecognized → default (not True)", OF.get_bool("t.bool", False) is False)
ok("get_bool unset → default", OF.get_bool("t.never", True) is True)

# ── enum: unknown → default; invalid write → ValueError ─────────────────────────────
ok("get_enum unset → default", OF.get_enum("t.enum", {"a", "b"}, "a") == "a")
OF.set_enum("t.enum", "b", {"a", "b"})
ok("get_enum reads a stored allowed value", OF.get_enum("t.enum", {"a", "b"}, "a") == "b")
OF.set_str("t.enum", "zzz")
ok("get_enum unknown stored → default", OF.get_enum("t.enum", {"a", "b"}, "a") == "a")
_ve = False
try:
    OF.set_enum("t.enum", "nope", {"a", "b"})
except ValueError:
    _ve = True
ok("set_enum rejects an invalid value with ValueError", _ve)

# ── reads never raise even when the DB layer explodes ───────────────────────────────
_orig = OF.get_connection
OF.get_connection = lambda: (_ for _ in ()).throw(RuntimeError("boom"))
ok("get_str never raises on DB error", OF.get_str("x", "def") == "def")
ok("get_bool never raises on DB error", OF.get_bool("x", True) is True)
ok("get_enum never raises on DB error", OF.get_enum("x", {"a"}, "a") == "a")
ok("all_flags never raises on DB error", OF.all_flags() == {})
OF.get_connection = _orig

# ── behavior parity: every migrated flag's no-row default is byte-identical ──────────
from core import chat_modes, premium_readers, terminal_engine, office_artifacts, chat_runtime  # noqa: E402

conn = get_connection()
conn.execute("DELETE FROM owner_settings")  # clear seeds so we test true no-row defaults
conn.commit()
conn.close()
ok("chat.mode_v2 no-row default = True", chat_modes.mode_v2_enabled() is True)
ok("chat.premium_readers no-row default matches ENABLE_PREMIUM_READERS",
   premium_readers.premium_readers_enabled() is premium_readers.ENABLE_PREMIUM_READERS)
ok("terminal.mode no-row default = DEFAULT_MODE", terminal_engine.get_mode() == terminal_engine.DEFAULT_MODE)
ok("terminal.enabled no-row default = True", terminal_engine.is_enabled() is True)
ok("office.v3_enabled no-row default is truthy", office_artifacts.v3_enabled() is True)
ok("chat_runtime_v2 no-row default = 'on'", chat_runtime.runtime_mode() == "on")
OF.set_str(chat_runtime.RUNTIME_FLAG, "garbage")
ok("chat_runtime_v2 garbage value fails open to 'on'", chat_runtime.runtime_mode() == "on")

# ── the new #20 flags default off; brain_v2_mode precedence ──────────────────────────
ok("brain.v2_enabled defaults False", OF.get_bool(OF.BRAIN_V2_ENABLED, False) is False)
ok("brain.v2_shadow defaults False", OF.get_bool(OF.BRAIN_V2_SHADOW, False) is False)
ok("architecture.v2_enabled defaults False", OF.get_bool(OF.ARCHITECTURE_V2_ENABLED, False) is False)
ok("brain_v2_mode default off", OF.brain_v2_mode() == "off")
OF.set_bool(OF.BRAIN_V2_SHADOW, True)
ok("brain_v2_mode shadow when only shadow set", OF.brain_v2_mode() == "shadow")
OF.set_bool(OF.BRAIN_V2_ENABLED, True)
ok("brain_v2_mode on when enabled (enabled wins over shadow)", OF.brain_v2_mode() == "on")

# ── vault active-slot round-trips through the shared ensure_schema ───────────────────
from core import vault  # noqa: E402

conn = get_connection()
vault._set_active_label(conn, "GITHUB_TOKEN", "Key 2")
ok("vault active-slot label round-trips via owner_flags.ensure_schema",
   vault._get_active_label(conn, "GITHUB_TOKEN") == "Key 2")
vault._set_active_label(conn, "GITHUB_TOKEN", None)
ok("vault active-slot clear round-trips", vault._get_active_label(conn, "GITHUB_TOKEN") is None)
conn.close()

print(f"\n🎉 ALL {PASS} CHECKS PASSED")
