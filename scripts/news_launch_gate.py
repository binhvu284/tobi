"""#23 News Page V2 launch gate — one command instead of a checklist.

The plan (§11/§12) says the flag may only be turned on after three things pass: the
test suites, seven consecutive clean refresh runs, and a twenty-item evidence review.
Two of those are machine-checkable and one needs the owner's eyes. This script runs
all three in order and prints a verdict, so the review is *reading a table* rather
than *knowing what to look for*.

    python scripts/news_launch_gate.py                # everything (needs the network)
    python scripts/news_launch_gate.py --suites-only  # just the test suites, offline
    python scripts/news_launch_gate.py --runs 7       # how many refresh rounds

What each stage means:

1. **Suites** — the 12 automated News suites. All must pass.
2. **Refresh runs** — one full Home+Trending+Feed collection round, repeated. A round
   counts as clean when no source failed. This is the "seven consecutive local refresh
   runs" gate; it needs the internet and takes a few minutes per round.
3. **Evidence** — twenty real items sampled from the feed, each shown with its source,
   its link and its timestamp. The checks that can be automated are: every item has a
   real source, a real link and a real date (nothing fabricated), no more than three
   in a row from one source, and no one topic over 40%. The two judgement calls —
   *is it trustworthy* and *is it interesting* — are yours; the table is laid out so
   you can mark them off as you read.

Nothing here flips a flag. It tells you whether you may.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# A Windows console defaults to a legacy codepage that cannot print the box-drawing and
# quote characters below; without this the gate would crash on its own first heading.
for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

SUITES = [
    "test_news_v2_schema", "test_news_v2_sources", "test_news_v2_refresh",
    "test_news_v2_interactions", "test_news_v2_ranking", "test_news_v2_api",
    "test_news_v2_rollout", "test_news_v2_media", "test_news_v2_llm",
    "test_news_v2_recap", "test_news_v2_spotlight", "test_news_v2_context_brain",
]
SAMPLE = 20
MAX_CONSECUTIVE_PER_SOURCE = 3
MAX_TOPIC_SHARE = 0.40

GREEN, RED, DIM, BOLD, OFF = "\033[32m", "\033[31m", "\033[2m", "\033[1m", "\033[0m"


def head(text: str) -> None:
    print(f"\n{BOLD}{text}{OFF}\n{'─' * max(len(text), 40)}")


def verdict(passed: bool, text: str) -> None:
    print(f"  {GREEN + 'PASS' if passed else RED + 'FAIL'}{OFF}  {text}")


# ── stage 1: the suites ──────────────────────────────────────────────────────────────
def run_suites() -> bool:
    head("1. Automated suites")
    python = str(ROOT.parent / ".python" / "venv" / "Scripts" / "python.exe")
    if not Path(python).is_file():
        python = sys.executable
    all_ok = True
    for name in SUITES:
        proc = subprocess.run([python, str(ROOT / "tests" / f"{name}.py")],
                              capture_output=True, text=True, cwd=str(ROOT))
        tail = [ln for ln in (proc.stdout or "").splitlines() if ln.strip()]
        ok = proc.returncode == 0
        all_ok &= ok
        print(f"  {GREEN + 'PASS' if ok else RED + 'FAIL'}{OFF}  {name:<32} "
              f"{tail[-1][:60] if tail else ''}")
        if not ok:
            for line in (tail[-6:] if tail else []) + (proc.stderr or "").splitlines()[-6:]:
                print(f"        {DIM}{line[:150]}{OFF}")
    return all_ok


# ── stage 2: consecutive clean refresh runs ──────────────────────────────────────────
def run_refreshes(rounds: int) -> bool:
    head(f"2. {rounds} consecutive clean refresh runs")
    from core import owner_flags
    from core.news import refresh
    if not (owner_flags.get_bool(owner_flags.NEWS_V2_ENABLED, False)
            or owner_flags.get_bool(owner_flags.NEWS_V2_SHADOW, False)):
        print(f"  {RED}News collection is off.{OFF} Turn on shadow collection first — it fills the "
              f"News tables while the old page stays live:\n"
              f"      python -c \"from core import owner_flags; "
              f"owner_flags.set_bool(owner_flags.NEWS_V2_SHADOW, True)\"\n"
              f"  Then restart Mission Control and run this again.")
        return False
    streak = 0
    for round_no in range(1, rounds + 1):
        dirty = []
        for tab in ("home", "trending", "feed"):
            job = refresh.request_refresh(tab)
            done = refresh.run_job(job["job_id"])
            state = str(done.get("state"))
            failed = sorted(s for s, cp in (done.get("checkpoints") or {}).items()
                            if cp.get("state") == "failed")
            if state != "completed" or failed:
                dirty.append(f"{tab}={state}" + (f" ({', '.join(failed)})" if failed else ""))
        if dirty:
            streak = 0
            print(f"  {RED}FAIL{OFF}  round {round_no}: {'; '.join(dirty)}")
        else:
            streak += 1
            print(f"  {GREEN}PASS{OFF}  round {round_no}: home, trending and feed all clean "
                  f"(streak {streak}/{rounds})")
    return streak >= rounds


# ── stage 3: the twenty-item evidence review ─────────────────────────────────────────
def evidence_review() -> bool:
    head(f"3. Evidence review — {SAMPLE} items")
    from core.database import get_connection
    from core.news import reader
    conn = get_connection()
    try:
        items = reader.read(section="feed", limit=SAMPLE, conn=conn).get("items") or []
    finally:
        conn.close()
    if len(items) < SAMPLE:
        print(f"  {RED}Only {len(items)} items collected — need {SAMPLE}.{OFF} "
              f"Run more refresh rounds first.")
        return False

    print(f"  {DIM}Read down the list. Mark an item bad if you do not trust it or it is not "
          f"interesting.\n  The gate wants at least 16 of 20 trustworthy and at least 14 of 20 "
          f"interesting.{OFF}\n")
    fabricated, missing_reason = [], []
    for i, item in enumerate(items, 1):
        has_evidence = bool(item.get("source") and item.get("url") and item.get("published_at"))
        if not has_evidence:
            fabricated.append(i)
        why = [w for w in (item.get("why_shown") or []) if w]
        if not why:
            missing_reason.append(i)
        print(f"  {i:>2}. {(item.get('title') or '')[:78]}")
        print(f"      {DIM}{item.get('source') or '(no source)'} · "
              f"{item.get('published_at') or '(no date)'} · {(item.get('url') or '(no link)')[:70]}{OFF}")
        if why:
            print(f"      {DIM}why: {'; '.join(why)[:100]}{OFF}")

    print()
    verdict(not fabricated,
            "every item has a real source, link and date"
            + (f" — missing on #{', #'.join(map(str, fabricated))}" if fabricated else ""))

    sources = [i.get("source") for i in items]
    longest, run = 1, 1
    for a, b in zip(sources, sources[1:]):
        run = run + 1 if a == b else 1
        longest = max(longest, run)
    verdict(longest <= MAX_CONSECUTIVE_PER_SOURCE,
            f"no more than {MAX_CONSECUTIVE_PER_SOURCE} in a row from one source "
            f"(longest run: {longest})")

    topics = Counter((i.get("title") or "").split(" ")[0].lower() for i in items)
    top_topic, top_count = (topics.most_common(1) or [("", 0)])[0]
    share = top_count / len(items)
    verdict(share <= MAX_TOPIC_SHARE,
            f"no single topic over {int(MAX_TOPIC_SHARE * 100)}% "
            f"(largest: “{top_topic}” at {int(share * 100)}%)")

    verdict(not missing_reason,
            "every item explains why it was shown"
            + (f" — missing on #{', #'.join(map(str, missing_reason))}" if missing_reason else ""))

    print(f"\n  {DIM}Still yours to judge: are at least 16 trustworthy, and at least 14 "
          f"worth reading?{OFF}")
    return not fabricated and longest <= MAX_CONSECUTIVE_PER_SOURCE and share <= MAX_TOPIC_SHARE


def main() -> int:
    ap = argparse.ArgumentParser(description="#23 News V2 launch gate")
    ap.add_argument("--runs", type=int, default=7, help="consecutive clean refresh rounds required")
    ap.add_argument("--suites-only", action="store_true", help="skip the network stages")
    args = ap.parse_args()

    results = {"suites": run_suites()}
    if not args.suites_only:
        results["refresh runs"] = run_refreshes(args.runs)
        results["evidence"] = evidence_review()

    head("Verdict")
    for name, passed in results.items():
        verdict(passed, name)
    if all(results.values()) and not args.suites_only:
        print(f"\n  {GREEN}Every automated gate passes.{OFF} If the twenty items read well to you and "
              f"the page looks right in your themes, turn News V2 on:\n"
              f"      python -c \"from core import owner_flags; "
              f"owner_flags.set_bool(owner_flags.NEWS_V2_ENABLED, True)\"\n"
              f"  {DIM}To go back at any time, set that to False — the old page and its data are "
              f"untouched.{OFF}")
    elif args.suites_only:
        print(f"\n  {DIM}Suites only. Run without --suites-only for the refresh and evidence "
              f"gates.{OFF}")
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
