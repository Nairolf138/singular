"""Command line interface for singular."""

from __future__ import annotations

import argparse
import random
from pathlib import Path
from typing import Callable, Any

from .organisms.birth import birth
from .organisms.talk import talk
from .organisms.status import status
from .runs.run import run as run_run
from .runs.synthesize import synthesize
from .runs.report import report
from .runs.loop import loop as loop_run
Command = Callable[..., Any]


def main(argv: list[str] | None = None) -> int:
    """Run the singular command line interface."""

    parser = argparse.ArgumentParser(prog="singular")
    parser.add_argument(
        "--seed", type=int, default=None, help="Random seed for reproducibility"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("birth", help="Birth a new organism").set_defaults(func=birth)
    subparsers.add_parser("run", help="Execute a run").set_defaults(func=run_run)
    loop_parser = subparsers.add_parser("loop", help="Execute evolutionary loop")
    loop_parser.add_argument("--skills-dir", type=Path, default=Path("skills"))
    loop_parser.add_argument(
        "--checkpoint", type=Path, default=Path("life_checkpoint.json")
    )
    loop_parser.add_argument("--budget-seconds", type=float, required=True)
    loop_parser.add_argument("--run-id", default="loop", help="Run identifier")
    loop_parser.set_defaults(func=loop_run)

    subparsers.add_parser("status", help="Show current status").set_defaults(func=status)

    talk_parser = subparsers.add_parser("talk", help="Talk with the system")
    talk_parser.add_argument("--provider", default=None, help="LLM provider to use")
    talk_parser.set_defaults(func=talk)

    subparsers.add_parser("synthesize", help="Synthesize results").set_defaults(func=synthesize)
    report_parser = subparsers.add_parser(
        "report", help="Summarize performance from a run"
    )
    report_parser.add_argument("--id", required=True, help="Run identifier")
    report_parser.set_defaults(func=report)

    args = parser.parse_args(argv)

    if args.seed is not None:
        random.seed(args.seed)

    func: Command = args.func
    if args.command == "report":
        func(run_id=args.id, seed=args.seed)
    elif args.command == "talk":
        func(provider=args.provider, seed=args.seed)
    elif args.command == "loop":
        func(
            skills_dir=args.skills_dir,
            checkpoint=args.checkpoint,
            budget_seconds=args.budget_seconds,
            run_id=args.run_id,
            seed=args.seed,
        )
    else:
        func(seed=args.seed)
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
