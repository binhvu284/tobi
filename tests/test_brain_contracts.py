"""
BRAIN MEMORY V2 contracts (queue #20, T01) — pure value types + scoring + gate.

No DB needed; plain python, no pytest:
    python tests/test_brain_contracts.py

Covers: the 10-member type enum; weighted quality scoring; candidate validation
(rejects malformed/unvalidated input, scope-key requirement, 320-char evidence
cap); and every activation-gate branch (reject / pending / active, plus the
sensitive, inferred, low-confidence, conflict, and hard-rule pending paths).
"""
import os
import sys
import tempfile

os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="tobi_bc_"), "agent.db")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from core.brain_contracts import (  # noqa: E402
    MemoryType, ScopeType, Authority, Explicitness, Trust, MemoryStatus,
    MemoryCandidate, activation_gate, compute_quality_score,
    QUALITY_WEIGHTS, MAX_EVIDENCE_CHARS,
)

PASS = 0


def ok(name: str, cond: bool, detail: str = ""):
    global PASS
    if not cond:
        print(f"❌ {name} {detail}")
        sys.exit(1)
    PASS += 1
    print(f"✅ {name}")


def raises(fn, exc=ValueError) -> bool:
    try:
        fn()
    except exc:
        return True
    except Exception:
        return False
    return False


def cand(**kw) -> MemoryCandidate:
    base = dict(distilled_text="Owner prefers concise replies", memory_type=MemoryType.PREFERENCE)
    base.update(kw)
    return MemoryCandidate(**base)


# ── enum + weights ───────────────────────────────────────────────────────────
ok("MemoryType has 10 members", len(list(MemoryType)) == 10, str(len(list(MemoryType))))
ok("MemoryType values", {t.value for t in MemoryType} == {
    "fact", "identity", "preference", "correction", "behavior_rule", "workflow_standard",
    "frustration_trigger", "decision", "project_context", "relationship"})
ok("quality weights sum to 100", sum(QUALITY_WEIGHTS.values()) == 100)

# ── scoring ──────────────────────────────────────────────────────────────────
ok("score all-1.0 == 100", compute_quality_score(1, 1, 1, 1, 1, 1) == 100.0)
ok("score all-0 == 0", compute_quality_score(0, 0, 0, 0, 0, 0) == 0.0)
ok("score weighted (dur+act) == 44", compute_quality_score(1, 1, 0, 0, 0, 0) == 44.0,
   str(compute_quality_score(1, 1, 0, 0, 0, 0)))
ok("score rejects out-of-range dim", raises(lambda: compute_quality_score(2, 0, 0, 0, 0, 0)))

# ── candidate validation ─────────────────────────────────────────────────────
c = cand(durability=1, actionability=1)
ok("valid candidate computes quality_score", c.quality_score == 44.0, str(c.quality_score))
ok("empty distilled_text rejected", raises(lambda: cand(distilled_text="   ")))
ok("non-enum memory_type rejected",
   raises(lambda: MemoryCandidate(distilled_text="x", memory_type="preference")))
ok("confidence > 1 rejected", raises(lambda: cand(confidence=1.5)))
ok("confidence bool rejected", raises(lambda: cand(confidence=True)))
ok("dimension > 1 rejected", raises(lambda: cand(durability=2.0)))
ok("evidence over 320 rejected", raises(lambda: cand(evidence_excerpt="x" * (MAX_EVIDENCE_CHARS + 1))))
ok("evidence exactly 320 ok", cand(evidence_excerpt="x" * MAX_EVIDENCE_CHARS).evidence_excerpt.startswith("x"))
ok("scoped memory without key rejected", raises(lambda: cand(scope_type=ScopeType.PROJECT)))
ok("scoped memory with key ok", cand(scope_type=ScopeType.PROJECT, scope_key="proj-1").scope_key == "proj-1")
ok("tags must be tuple (list rejected)", raises(lambda: cand(tags=["a"])))
ok("sensitive must be bool (int rejected)", raises(lambda: cand(sensitive=1)))
ok("explicit quality_score is kept, not recomputed", cand(quality_score=55.0).quality_score == 55.0)
ok("quality_score > 100 rejected", raises(lambda: cand(quality_score=150.0)))
ok("is_hard_rule reflects authority", cand(authority=Authority.HARD).is_hard_rule is True)

# ── activation gate ──────────────────────────────────────────────────────────
def gate(**kw):
    base = dict(quality_score=80.0, confidence=0.9, explicitness=Explicitness.EXPLICIT,
                authority=Authority.SOFT, sensitive=False)
    base.update(kw)
    return activation_gate(cand(**base))

ok("score < 35 → rejected", activation_gate(cand(quality_score=20.0)) is MemoryStatus.REJECTED)
ok("35 <= score < 70 → pending", activation_gate(cand(quality_score=50.0)) is MemoryStatus.PENDING)
ok("strong explicit soft → active", gate() is MemoryStatus.ACTIVE)
ok("sensitive → pending", gate(sensitive=True) is MemoryStatus.PENDING)
ok("inferred → pending", gate(explicitness=Explicitness.INFERRED) is MemoryStatus.PENDING)
ok("low confidence → pending", gate(confidence=0.5) is MemoryStatus.PENDING)
ok("hard rule → pending (always needs approval)", gate(authority=Authority.HARD) is MemoryStatus.PENDING)
ok("conflict → pending",
   activation_gate(cand(quality_score=80.0, confidence=0.9, explicitness=Explicitness.EXPLICIT),
                   has_conflict=True) is MemoryStatus.PENDING)
ok("untrusted soft can still activate (only hard rules are barred)",
   gate(trust=Trust.UNTRUSTED) is MemoryStatus.ACTIVE)
ok("untrusted hard → pending", gate(authority=Authority.HARD, trust=Trust.UNTRUSTED) is MemoryStatus.PENDING)
ok("exactly 70 + all gates → active", gate(quality_score=70.0) is MemoryStatus.ACTIVE)
ok("confidence exactly 0.85 → active", gate(confidence=0.85) is MemoryStatus.ACTIVE)

print(f"\n{PASS} checks passed")
