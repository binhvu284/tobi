"""Local command for rebuilding Runtime V2 projections from event history."""
from __future__ import annotations

import argparse
import json
from typing import Optional

from core.runtime.projections import (
    rebuild_all_projections,
    rebuild_run_projection,
    rebuild_system_projection,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Rebuild Mission Control Runtime V2 projections")
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--run", metavar="RUN_ID", help="rebuild one run projection")
    target.add_argument("--system", action="store_true", help="rebuild the System Model projection")
    target.add_argument("--all", action="store_true", help="rebuild every projection")
    parser.add_argument("--verify", action="store_true", help="rebuild twice and compare state hashes")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = _parser().parse_args(argv)
    if args.run:
        first = rebuild_run_projection(args.run)
        if args.verify and first != rebuild_run_projection(args.run):
            raise RuntimeError("run projection rebuild is not deterministic")
        result = {**first, "verified": args.verify}
    elif args.system:
        first = rebuild_system_projection()
        if args.verify and first != rebuild_system_projection():
            raise RuntimeError("system projection rebuild is not deterministic")
        result = {**first, "verified": args.verify}
    else:
        result = rebuild_all_projections(verify=args.verify)
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
