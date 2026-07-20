"""
Brain Memory V2 repository boundary (queue #20, T02) — save/read/list, sensitive
vault encryption, locked-vault redaction + context exclusion, purge, and the
compatibility-leak guard.

Plain python, no pytest, isolated temp DB:
    python tests/test_brain_repository.py

Acceptance (spec T02): sensitive content is encrypted at rest, redacted while the
vault is locked, excluded from LLM context while locked, purged permanently on
owner deletion, and never reachable through the legacy brain_memories table.
"""
import os
import sys
import tempfile

os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="tobi_br_"), "agent.db")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from core.database import init_database, get_connection  # noqa: E402
from core import vault  # noqa: E402
from core import brain_repository as repo  # noqa: E402
from core.brain_repository import REDACTED, StoredMemory  # noqa: E402
from core.brain_contracts import (  # noqa: E402
    MemoryCandidate, MemoryType, ScopeType, Authority, Explicitness, Trust,
    MemoryStatus, LinkType,
)

init_database()
conn = get_connection()
vault.setup(conn, "master-pass-123456", import_env=False)  # leaves vault unlocked

PASS = 0


def ok(name: str, cond: bool, detail: str = ""):
    global PASS
    if not cond:
        print(f"❌ {name} {detail}")
        sys.exit(1)
    PASS += 1
    print(f"✅ {name}")


def raises(fn, exc=Exception) -> bool:
    try:
        fn()
    except exc:
        return True
    except Exception:
        return False
    return False


def count(sql, args=()):
    return conn.execute(sql, args).fetchone()[0]


# ── non-sensitive roundtrip (default status via activation gate) ─────────────
strong = MemoryCandidate(
    distilled_text="Owner prefers concise, direct replies",
    memory_type=MemoryType.PREFERENCE,
    behavior_implication="Keep answers short unless asked to expand",
    tags=("tone", "style"),
    scope_type=ScopeType.PROJECT, scope_key="tobi",
    authority=Authority.SOFT, explicitness=Explicitness.EXPLICIT, confidence=0.9,
    durability=1, actionability=1, specificity=1, source_strength=1,  # score 76 → active-eligible
    suggested_usage="Trim preamble in Chat replies",
    evidence_excerpt="the owner said 'just give me the answer'",
    source_ref="chat:2026-07-17", trust=Trust.TRUSTED, sensitive=False,
)
mid = repo.save(strong, conn=conn)
m = repo.read(mid, conn=conn)
ok("save returns id", isinstance(mid, int) and mid > 0)
ok("read returns StoredMemory", isinstance(m, StoredMemory))
ok("distilled_text roundtrips", m.distilled_text == "Owner prefers concise, direct replies")
ok("memory_type is enum", m.memory_type is MemoryType.PREFERENCE)
ok("tags roundtrip as tuple", m.tags == ("tone", "style"))
ok("scope roundtrips", m.scope_type is ScopeType.PROJECT and m.scope_key == "tobi")
ok("authority/explicitness enums", m.authority is Authority.SOFT and m.explicitness is Explicitness.EXPLICIT)
ok("quality dims roundtrip", (m.durability, m.actionability, m.specificity, m.source_strength) == (1, 1, 1, 1))
ok("quality_score computed", m.quality_score == 76.0, str(m.quality_score))
ok("default status = activation gate (active)", m.status is MemoryStatus.ACTIVE)
ok("not sensitive, not redacted", m.sensitive is False and m.redacted is False)
ok("evidence roundtrips", len(m.evidence) == 1 and m.evidence[0].excerpt == "the owner said 'just give me the answer'")

# list
ok("list_memories includes it", any(x.id == mid for x in repo.list_memories(conn=conn)))
ok("list by status=active includes it", any(x.id == mid for x in repo.list_memories(MemoryStatus.ACTIVE, conn=conn)))
ok("list by status=rejected excludes it", all(x.id != mid for x in repo.list_memories(MemoryStatus.REJECTED, conn=conn)))

# ── sensitive memory: encrypted at rest ──────────────────────────────────────
SECRET_TEXT = "Owner's home safe code is SUPER_SECRET_8842"
SECRET_EV = "he told me the code SUPER_SECRET_8842 on the call"
secret = MemoryCandidate(
    distilled_text=SECRET_TEXT, memory_type=MemoryType.FACT,
    behavior_implication="Guard the code SUPER_SECRET_8842 — never speak it aloud",
    authority=Authority.SOFT, explicitness=Explicitness.EXPLICIT, confidence=0.95,
    durability=1, actionability=1, specificity=1, source_strength=1,
    evidence_excerpt=SECRET_EV, source_ref="call:2026-07-17", sensitive=True,
)
sid = repo.save(secret, conn=conn)
ok("sensitive save → pending (gate bars sensitive)", repo.read(sid, conn=conn).status is MemoryStatus.PENDING)

# plaintext columns hold the sentinel, never the secret
db_distilled = conn.execute("SELECT distilled_text FROM brain_memory_v2 WHERE id=?", (sid,)).fetchone()[0]
db_excerpt = conn.execute("SELECT excerpt FROM brain_memory_evidence WHERE memory_id=?", (sid,)).fetchone()[0]
db_impl = conn.execute("SELECT behavior_implication FROM brain_memory_v2 WHERE id=?", (sid,)).fetchone()[0]
ok("v2 distilled column is redacted sentinel", db_distilled == REDACTED, db_distilled)
ok("evidence excerpt column is redacted sentinel", db_excerpt == REDACTED, db_excerpt)
ok("v2 behavior_implication column is redacted sentinel (#20 P1)", db_impl == REDACTED, db_impl)

# secure payloads exist, encrypted; plaintext absent from the ciphertext
payloads = conn.execute("SELECT field, ciphertext FROM brain_secure_payloads WHERE memory_id=?", (sid,)).fetchall()
fields = {p[0] for p in payloads}
ok("secure payload for distilled_text", "distilled_text" in fields)
ok("secure payload for behavior_implication (#20 P1)", "behavior_implication" in fields)
ok("secure payload for evidence", any(f.startswith("evidence:") for f in fields))
ok("plaintext not present in any ciphertext",
   all(b"SUPER_SECRET_8842" not in bytes(p[1]) for p in payloads))

# compatibility-leak guard: secret must not appear anywhere in legacy/plaintext stores
def secret_leaks_anywhere() -> bool:
    marker = "SUPER_SECRET_8842"
    for table, col in (("brain_memory_v2", "distilled_text"),
                       ("brain_memory_v2", "behavior_implication"),
                       ("brain_memory_evidence", "excerpt"),
                       ("brain_memories", "content")):
        try:
            rows = conn.execute(f"SELECT {col} FROM {table}").fetchall()
        except Exception:
            continue
        if any(marker in (str(r[0]) if r[0] is not None else "") for r in rows):
            return True
    return False
ok("secret does not leak into any plaintext/legacy column", not secret_leaks_anywhere())

# ── unlocked read reveals; context read includes ─────────────────────────────
sm = repo.read(sid, conn=conn)
ok("unlocked read reveals distilled_text", sm.distilled_text == SECRET_TEXT and sm.redacted is False)
ok("unlocked read reveals behavior_implication (#20 P1)",
   sm.behavior_implication == "Guard the code SUPER_SECRET_8842 — never speak it aloud")
ok("unlocked read reveals evidence", sm.evidence[0].excerpt == SECRET_EV and sm.evidence[0].redacted is False)
ok("unlocked context read includes sensitive", repo.read(sid, for_context=True, conn=conn) is not None)

# ── locked: redacted for UI, excluded from context ───────────────────────────
vault.lock()
locked = repo.read(sid, conn=conn)
ok("locked read redacts distilled_text", locked.distilled_text == REDACTED and locked.redacted is True)
ok("locked read redacts evidence", locked.evidence[0].excerpt == REDACTED and locked.evidence[0].redacted is True)
ok("locked context read excludes sensitive (None)", repo.read(sid, for_context=True, conn=conn) is None)
ok("locked context list excludes sensitive", all(x.id != sid for x in repo.list_memories(for_context=True, conn=conn)))
ok("locked context list still includes non-sensitive", any(x.id == mid for x in repo.list_memories(for_context=True, conn=conn)))
ok("locked non-context list still returns sensitive (redacted)",
   any(x.id == sid and x.redacted for x in repo.list_memories(conn=conn)))

# saving a new sensitive memory while locked fails closed, writes nothing
before = count("SELECT count(*) FROM brain_memory_v2")
ok("sensitive save while locked raises VaultLocked",
   raises(lambda: repo.save(secret, conn=conn), vault.VaultLocked))
ok("no partial row written on locked sensitive save", count("SELECT count(*) FROM brain_memory_v2") == before)

# non-sensitive save still works while locked
mid2 = repo.save(MemoryCandidate(distilled_text="Owner's timezone is UTC+7",
                                 memory_type=MemoryType.FACT, explicitness=Explicitness.EXPLICIT), conn=conn)
ok("non-sensitive save works while locked", repo.read(mid2, conn=conn).distilled_text == "Owner's timezone is UTC+7")

# ── re-unlock restores plaintext ─────────────────────────────────────────────
vault.unlock(conn, "master-pass-123456")
ok("re-unlock reveals distilled_text again", repo.read(sid, conn=conn).distilled_text == SECRET_TEXT)

# ── links + lifecycle ────────────────────────────────────────────────────────
repo.link(mid, mid2, LinkType.SUPPORTS, conn=conn)
ok("link row created", count("SELECT count(*) FROM brain_memory_links WHERE from_id=? AND to_id=?", (mid, mid2)) == 1)
ok("link rejects non-enum", raises(lambda: repo.link(mid, mid2, "supports", conn=conn), TypeError))

repo.archive(mid, conn=conn)
ok("archive is reversible (row kept, status archived)", repo.read(mid, conn=conn).status is MemoryStatus.ARCHIVED)
repo.set_status(mid, MemoryStatus.ACTIVE, conn=conn)
ok("status can be flipped back", repo.read(mid, conn=conn).status is MemoryStatus.ACTIVE)

# ── purge permanently removes memory + payload + children ────────────────────
ev_before = count("SELECT count(*) FROM brain_memory_evidence WHERE memory_id=?", (sid,))
ok("evidence present before purge", ev_before >= 1)
ok("purge returns True", repo.purge(sid, conn=conn) is True)
ok("purged memory unreadable", repo.read(sid, conn=conn) is None)
ok("purge removed v2 row", count("SELECT count(*) FROM brain_memory_v2 WHERE id=?", (sid,)) == 0)
ok("purge removed secure payload", count("SELECT count(*) FROM brain_secure_payloads WHERE memory_id=?", (sid,)) == 0)
ok("purge cascaded evidence", count("SELECT count(*) FROM brain_memory_evidence WHERE memory_id=?", (sid,)) == 0)
ok("purge of missing id returns False", repo.purge(999999, conn=conn) is False)

# ── boundary: only validated candidates cross in ─────────────────────────────
ok("save rejects a raw dict", raises(lambda: repo.save({"distilled_text": "x"}, conn=conn), TypeError))

print(f"\n{PASS} checks passed")
