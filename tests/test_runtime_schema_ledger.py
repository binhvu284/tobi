"""The runtime migration ledger has to actually record something.

Found on 2026-08-21 by the new one-click infrastructure check, on the owner's live database:
all 22 canonical tables present, and **none** of the 13 `mc-runtime-v2-*` versions recorded.

Two modules create the shared `schema_migrations` table, and they disagreed:

    core/chat_runtime.py    applied_at TEXT NOT NULL
    core/schema/runtime.py  applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP

`CREATE TABLE IF NOT EXISTS` means whoever runs first wins, and on that database Chat's runtime
won. The runtime schema then recorded its versions with

    INSERT OR IGNORE INTO schema_migrations (version) VALUES (?)

which violates `applied_at NOT NULL` — and `OR IGNORE` swallows a constraint violation without
a word. So the ledger stayed empty, `_schema_is_ready()` answered False forever, and the entire
runtime schema was re-applied at every one of its 62 call sites, on every runtime database
operation, for the life of the database. The ledger that exists to prevent exactly that had
been silently doing nothing.

The rule this suite enforces: a writer supplies the columns it needs rather than trusting a
table definition it does not own, and the ledger is checked by whether it *recorded* something,
never by whether the statement raised.

Isolated temp DB, plain python, no pytest:
    python tests/test_runtime_schema_ledger.py
"""
from __future__ import annotations

import os
import re
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TMP = tempfile.mkdtemp(prefix="tobi_schema_ledger_")
os.environ["DB_PATH"] = os.path.join(TMP, "agent.db")

from core.schema.runtime import (  # noqa: E402
    RUNTIME_SCHEMA_VERSIONS,
    _ensure_runtime_schema,
    _schema_is_ready,
    _RUNTIME_TABLES,
)

FAILURES: list[str] = []


def ok(name: str, cond: bool, detail: str = "") -> None:
    print(f"{'PASS' if cond else 'FAIL'} {name}{('  -> ' + detail) if detail and not cond else ''}")
    if not cond:
        FAILURES.append(name)


def recorded(conn: sqlite3.Connection) -> set[str]:
    return {row[0] for row in conn.execute(
        "SELECT version FROM schema_migrations WHERE version LIKE 'mc-runtime-v2-%'").fetchall()}


def fresh_db(name: str, ledger_ddl: str | None) -> sqlite3.Connection:
    """A database where some other module may already have created the shared ledger."""
    conn = sqlite3.connect(os.path.join(TMP, name))
    if ledger_ddl:
        conn.execute(ledger_ddl)
        conn.commit()
    return conn


# The exact definition Chat's runtime creates, which is what the owner's database has.
CHAT_LEDGER = ("CREATE TABLE IF NOT EXISTS schema_migrations ("
               "version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)")

# --- 1. the live shape: another module created the ledger first -------------------------
conn = fresh_db("chat-first.db", CHAT_LEDGER)
_ensure_runtime_schema(conn)

ok("every runtime version is recorded even when another module owns the ledger",
   recorded(conn) == set(RUNTIME_SCHEMA_VERSIONS),
   f"{len(recorded(conn))} of {len(RUNTIME_SCHEMA_VERSIONS)} recorded")
ok("every applied row carries a timestamp",
   all(row[0] for row in conn.execute(
       "SELECT applied_at FROM schema_migrations WHERE version LIKE 'mc-runtime-v2-%'").fetchall()))
ok("all canonical tables exist",
   _RUNTIME_TABLES.issubset({row[0] for row in conn.execute(
       "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}))
ok("the schema then reports itself ready, so it is not re-applied forever",
   _schema_is_ready(conn) is True)
conn.close()

# --- 2. the ledger survives the connection that wrote it --------------------------------
conn = sqlite3.connect(os.path.join(TMP, "chat-first.db"))
ok("the record is committed, not lost when the connection closes",
   recorded(conn) == set(RUNTIME_SCHEMA_VERSIONS), f"{len(recorded(conn))} after reopen")
ok("a second run is a no-op because the ledger answers", _schema_is_ready(conn) is True)
conn.close()

# --- 3. the runtime owning the ledger works the same way --------------------------------
conn = fresh_db("runtime-first.db", None)
_ensure_runtime_schema(conn)
ok("a database the runtime creates itself records its versions too",
   recorded(conn) == set(RUNTIME_SCHEMA_VERSIONS), f"{len(recorded(conn))} recorded")
ok("and reports ready", _schema_is_ready(conn) is True)
conn.close()

# --- 4. the two definitions of the shared table must not drift again ---------------------
# Same table, two creators. If their column definitions differ, whichever module happens to run
# first silently decides what the other one is allowed to write.
def ledger_columns(source: str) -> set[str]:
    match = re.search(r"CREATE TABLE IF NOT EXISTS schema_migrations\s*\((.*?)\)",
                      source, re.S | re.I)
    body = match.group(1) if match else ""
    return {line.strip().split()[0].lower() for line in body.split(",") if line.strip()}


chat_source = (ROOT / "core" / "chat_runtime.py").read_text(encoding="utf-8")
runtime_source = (ROOT / "core" / "schema" / "runtime.py").read_text(encoding="utf-8")
ok("both creators of schema_migrations declare the same columns",
   ledger_columns(chat_source) == ledger_columns(runtime_source) == {"version", "applied_at"},
   f"chat={ledger_columns(chat_source)} runtime={ledger_columns(runtime_source)}")
ok("the runtime writes applied_at itself instead of trusting a default it does not own",
   "INSERT OR IGNORE INTO schema_migrations (version, applied_at)" in runtime_source,
   "the insert still omits applied_at")

print(f"\n{'ALL' if not FAILURES else str(len(FAILURES)) + ' OF'} "
      f"{'SCHEMA LEDGER CHECKS PASSED' if not FAILURES else 'CHECKS FAILED: ' + ', '.join(FAILURES)}")
raise SystemExit(1 if FAILURES else 0)
