"""Tool Discovery content-creator (#23) — pick + generate + feedback loop.

Plain python, isolated DB, LLM + media seams stubbed (no network, no spend). Proves:
one quality pick per refresh, the owner-feedback loop biases the pick immediately,
the spotlight is stored + labeled, and budget/no-LLM degrade to zero writes.
"""
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("DB_PATH", str(Path(tempfile.mkdtemp()) / "spot.db"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.database import init_database, get_connection  # noqa: E402
from core.news import spotlight, recap  # noqa: E402
from core.news import contracts as CT  # noqa: E402
from core.news import normalizer as N  # noqa: E402

init_database()
NOW = datetime(2026, 7, 24, 12, 0, tzinfo=timezone.utc)
PASS = 0


def ok(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print(f"PASS {name}")
    else:
        print(f"FAIL {name} {detail}")
        raise SystemExit(1)


def mk(source, ext, url, title, itype, engagement):
    return CT.SourceRecord(source=source, external_id=ext, url=url, title=title,
                           item_type=itype, trust=CT.TrustClass.COMMUNITY,
                           observed_at=NOW.isoformat(), published_at=NOW.isoformat(),
                           excerpt="A developer tool that does useful things.",
                           engagement=engagement, raw_hash=CT.payload_hash({"u": url}))


conn = get_connection()
N.ingest(conn, [
    mk("hackernews", "hn-1", "https://news.ycombinator.com/item?id=1", "Show HN: Flashy Tool", CT.ItemType.TOOL, 50),
    mk("github", "acme/rocket", "https://github.com/acme/rocket", "acme/rocket", CT.ItemType.REPO, 4000),
])
conn.commit()

# ── pick: highest engagement/trust wins with no feedback yet ──────────────────────────
best = spotlight.pick_spotlight(conn, now=NOW)
repo_id = conn.execute("SELECT id FROM news_items WHERE canonical_url LIKE '%acme/rocket%'").fetchone()[0]
hn_id = conn.execute("SELECT id FROM news_items WHERE canonical_url LIKE '%ycombinator%'").fetchone()[0]
ok("picks the strongest candidate (repo, 4000 stars) with no feedback", best == repo_id, f"{best} vs {repo_id}")

# ── generate: no LLM → no write; LLM available → stored + labeled ─────────────────────
spotlight._llm_complete = lambda user: None
ok("no LLM routing → no spotlight, no crash", spotlight.generate_spotlight(conn, repo_id, now=NOW) is False)
ok("the item keeps NULL recap when generation is skipped",
   conn.execute("SELECT recap FROM news_items WHERE id=?", (repo_id,)).fetchone()[0] is None)

captured = {}
def fake_llm(user):
    captured["user"] = user
    return "Rocket is a fast build tool.\n**Highlights**\n- Instant reloads\n- Tiny config\n**Best for:** frontend teams."
spotlight._llm_complete = fake_llm
spotlight._thumbnail = lambda conn, item_id, source, url: None   # skip network thumbnail in test
ok("with LLM available the spotlight is written", spotlight.generate_spotlight(conn, repo_id, now=NOW) is True)
stored = conn.execute("SELECT recap FROM news_items WHERE id=?", (repo_id,)).fetchone()[0]
ok("spotlight content is stored (rich, bulleted)", stored and "**Highlights**" in stored and "- Instant reloads" in stored)
ok("untrusted material is fenced in the prompt", "UNTRUSTED MATERIAL" in captured["user"] and "acme/rocket" in captured["user"])
ok("a spotlighted item is never re-generated (recap present)",
   spotlight.generate_spotlight(conn, repo_id, now=NOW) is False)

# ── feedback loop: a disliked source sinks below a neutral one on the next pick ───────
# reset the repo recap so it is pickable again, then inject a strong negative github
# delta (what a committed dislike produces) and confirm pick_spotlight consumes it.
conn.execute("UPDATE news_items SET recap=NULL WHERE id=?", (repo_id,))
conn.commit()
from core.news import personalization  # noqa: E402
_real_imm = personalization.immediate_adjustments
personalization.immediate_adjustments = lambda conn, now=None: {"github": -2.0}
pick2 = spotlight.pick_spotlight(conn, now=NOW)
ok("owner feedback (disliked source) immediately biases the next pick away from it",
   pick2 == hn_id, f"{pick2} vs hn {hn_id}")
personalization.immediate_adjustments = _real_imm
conn.execute("UPDATE news_items SET recap='done' WHERE id=?", (repo_id,))   # take repo out again
conn.commit()

# ── budget guard: over budget → skip ─────────────────────────────────────────────────
recap._budget_ok = lambda: False
ok("over budget → no spotlight (honest skip)", spotlight.generate_spotlight(conn, hn_id, now=NOW) is False)
recap._budget_ok = lambda: True

# ── run_for_refresh: exactly one spotlight per refresh ───────────────────────────────
fresh = spotlight.run_for_refresh(conn, now=NOW)
ok("run_for_refresh spotlights exactly one candidate", fresh["spotlighted"] == 1, str(fresh))
conn.close()

print(f"\nALL {PASS} CHECKS PASSED")
