"""Compute frozen TOBIval completion from repository evidence, never stored claims."""
from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from core.runtime.eval_scorers import available_scorers
from core.runtime.evals import EvalRepository
from tobival.metrics import calculate_ecr


def compute_eval_completion(
    repository: EvalRepository,
    *,
    case_refs: Iterable[tuple[str, str]] | None = None,
    owner_visible: bool = False,
) -> dict:
    """Derive ECR proof from immutable cases and their latest canonical results."""
    if not isinstance(repository, EvalRepository):
        raise ValueError("repository must be an EvalRepository")
    selected = set(case_refs) if case_refs is not None else None
    cases = [
        case for case in repository.list_cases()
        if selected is None or (case["eval_case_id"], case["version"]) in selected
    ]
    if not cases:
        raise ValueError("at least one persisted evaluation case is required")

    scorer_names = set(available_scorers())
    proof_by_case: dict[str, dict[str, bool]] = {}
    category_proofs: dict[str, list[dict[str, bool]]] = defaultdict(list)
    category_safety: dict[str, bool] = defaultdict(bool)
    for case in cases:
        runs = repository.list_runs(
            eval_case_id=case["eval_case_id"],
            eval_case_version=case["version"],
        )
        latest = runs[0] if runs else None
        proof = {
            "versioned_dataset": bool(case.get("fixture_hash") and case.get("contract_hash")),
            "runnable_end_to_end": latest is not None,
            "objective_scorer": case["scorer"] in scorer_names,
            "trace_evidence_linkage": bool(
                latest
                and latest.get("run_id")
                and latest.get("trace_id")
                and latest.get("evidence_refs")
            ),
            "enforced_gate": bool(case["release_gate"] or case["autonomy_gate"]),
            "owner_visibility": bool(owner_visible),
        }
        proof_by_case[case["eval_case_id"]] = proof
        category_proofs[case["category"]].append(proof)
        category_safety[case["category"]] = (
            category_safety[case["category"]] or bool(case["autonomy_gate"])
        )

    rows = []
    for category, proofs in sorted(category_proofs.items()):
        rows.append({
            "category": category,
            "safety_critical": category_safety[category],
            "proof": {
                component: all(proof[component] for proof in proofs)
                for component in proofs[0]
            },
        })
    result = calculate_ecr(rows)
    return {
        **result,
        "proof": proof_by_case,
        "case_count": len(cases),
        "source": "immutable_runtime_eval_evidence",
    }
