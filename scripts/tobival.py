"""Local CLI for the frozen #34 TOBIval baseline package."""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _source_revision() -> str:
    try:
        revision = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return "working-tree"
    return revision[:12] if len(revision) == 40 else "working-tree"


DEFAULT_ACCEPTANCE_DB_PATH = (
    ROOT / ".tobi" / "tobival" / f"acceptance-{_source_revision()}.db"
)
os.environ.setdefault("DB_PATH", str(DEFAULT_ACCEPTANCE_DB_PATH))

from tobival.baseline import build_unchanged_baseline  # noqa: E402
from tobival.acceptance import FINAL_ACCEPTANCE_PATH, run_final_acceptance  # noqa: E402
from tobival.dataset import (  # noqa: E402
    DATASET_VERSION,
    build_dataset_lock,
    load_benchmark_contract,
    load_baseline_observations,
    load_cases,
    verify_dataset_lock,
)
from tobival.model_lane import ModelLaneError, run_model_baseline  # noqa: E402


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TOBIval T00 dataset and baseline tooling")
    parser.add_argument("--version", default=DATASET_VERSION)
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("verify", help="verify frozen files, counts, and benchmark approval")
    freeze = subcommands.add_parser("freeze", help="write the dataset hash lock")
    freeze.add_argument("--confirm", action="store_true", help="confirm intentional lock replacement")
    baseline = subcommands.add_parser("baseline", help="build the unchanged-code baseline report")
    baseline.add_argument("--output", type=Path)
    model_baseline = subcommands.add_parser(
        "run-model-baseline", help="run the owner-approved strong and weak model lanes"
    )
    model_baseline.add_argument("--output", type=Path)
    model_baseline.add_argument(
        "--replace", action="store_true", help="allow replacement of an existing model artifact"
    )
    model_baseline.add_argument(
        "--confirm", action="store_true", help="confirm intentional replacement"
    )
    acceptance = subcommands.add_parser(
        "acceptance", help="run all frozen cases and guarded holdouts"
    )
    acceptance.add_argument(
        "--output",
        type=Path,
        default=FINAL_ACCEPTANCE_PATH,
        help="write the bounded report (default: canonical final-acceptance artifact)",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.command == "freeze":
        if not args.confirm:
            print("Refusing to replace the lock without --confirm", file=sys.stderr)
            return 2
        directory = ROOT / "tests" / "evals" / args.version
        _write_json(directory / "manifest.lock.json", build_dataset_lock(args.version))
        print(f"Frozen TOBIval dataset {args.version}")
        return 0

    if args.command == "verify":
        lock = verify_dataset_lock(args.version)
        cases = load_cases(args.version, include_holdouts=True, purpose="final_acceptance")
        benchmark = load_benchmark_contract(args.version)
        print(json.dumps({
            **lock,
            "case_count": len(cases),
            "holdout_count": sum(case["holdout"] for case in cases),
            "benchmark_approval": benchmark["approval"]["status"],
        }, indent=2, sort_keys=True))
        return 0

    if args.command == "run-model-baseline":
        observations = load_baseline_observations(args.version)
        output = args.output or (
            ROOT / "tests" / "evals" / "baselines" / observations["production_commit"]
            / "model_runs.json"
        )
        if output.exists() and not (args.replace and args.confirm):
            print(
                "Refusing to replace the immutable model artifact without --replace --confirm",
                file=sys.stderr,
            )
            return 2
        try:
            report = run_model_baseline(args.version)
        except ModelLaneError as exc:
            print(f"Model baseline blocked: {exc}", file=sys.stderr)
            return 2
        _write_json(output, report)
        print(json.dumps({
            "output": str(output),
            "run_count": len(report["runs"]),
            "cost_usd": report["cost_usd"],
            "duration_seconds": report["duration_seconds"],
        }, indent=2, sort_keys=True))
        return 0

    if args.command == "acceptance":
        benchmark = load_benchmark_contract(args.version)
        cases = load_cases(
            args.version, include_holdouts=True, purpose="final_acceptance",
        )
        planned_calls = (
            sum(bool(case["model_dependent"]) for case in cases)
            * int(benchmark["model_repetitions"])
            * 2
        )
        print(
            f"Running final acceptance with {planned_calls} approved model calls. "
            f"Database: {os.environ['DB_PATH']}",
            file=sys.stderr,
            flush=True,
        )
        try:
            report = run_final_acceptance(args.version)
        except sqlite3.Error as exc:
            print(
                f"Acceptance database could not be opened at {os.environ['DB_PATH']}: {exc}",
                file=sys.stderr,
            )
            return 2
        except ModelLaneError as exc:
            print(f"Final acceptance blocked: {exc}", file=sys.stderr)
            return 2
        _write_json(args.output, report)
        quality = report["model_quality"]
        print(json.dumps({
            "case_count": report["case_count"],
            "holdout_passed": report["holdouts"]["passed"],
            "ecr": report["metrics"]["ecr"]["overall"],
            "ldr": report["metrics"]["ldr"],
            "model_responses": quality["model_responses"],
            "provider_failures": quality["provider_failures"],
            "raw_model_pass_rate": quality["raw_pass_rate"],
            "recovery_rate": quality["recovery_rate"],
            "cost_usd": report["cost_usd"],
            "duration_seconds": report["duration_seconds"],
            "release_ready": report["release_ready"],
            "blockers": report["blockers"],
            "database": os.environ["DB_PATH"],
            "output": str(args.output),
        }, indent=2, sort_keys=True))
        return 0 if report["release_ready"] else 1

    report = build_unchanged_baseline(args.version)
    if args.output:
        _write_json(args.output, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
