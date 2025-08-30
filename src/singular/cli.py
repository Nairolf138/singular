"""Command line interface for singular."""

from __future__ import annotations

import argparse
import random
from pathlib import Path
from typing import Callable, Any
import os

# Pre-parse ``--home`` before importing modules that depend on it
_early_parser = argparse.ArgumentParser(add_help=False)
_early_parser.add_argument("--home", type=Path)
_early_args, _ = _early_parser.parse_known_args()
if _early_args.home:
    os.environ["SINGULAR_HOME"] = str(_early_args.home)

from .organisms.birth import birth
from .organisms.spawn import spawn
from .organisms.talk import talk
from .organisms.status import status
from .organisms.quest import quest
from .runs.run import run as run_run
from .runs.synthesize import synthesize
from .runs.report import report
from .runs.loop import loop as loop_run
from .dashboard import run as dashboard_run

__all__ = ["main"]

Command = Callable[..., Any]


def main(argv: list[str] | None = None) -> int:
    """Run the singular command line interface."""

    parser = argparse.ArgumentParser(prog="singular")
    parser.add_argument(
        "--seed", type=int, default=None, help="Random seed for reproducibility"
    )
    parser.add_argument(
        "--home",
        type=Path,
        default=os.environ.get("SINGULAR_HOME"),
        help="Base directory for mem/ and runs/ (env: SINGULAR_HOME)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("birth", help="Birth a new organism").set_defaults(func=birth)
    spawn_parser = subparsers.add_parser(
        "spawn", help="Create child organism from two parents"
    )
    spawn_parser.add_argument("parent_a", type=Path)
    spawn_parser.add_argument("parent_b", type=Path)
    spawn_parser.add_argument("--out-dir", type=Path, default=None)
    spawn_parser.set_defaults(func=spawn)
    subparsers.add_parser("run", help="Execute a run").set_defaults(func=run_run)
    loop_parser = subparsers.add_parser("loop", help="Execute evolutionary loop")
    loop_parser.add_argument("--skills-dir", type=Path, default=Path("skills"))
    loop_parser.add_argument(
        "--checkpoint", type=Path, default=Path("life_checkpoint.json")
    )
    loop_parser.add_argument("--budget-seconds", type=float, required=True)
    loop_parser.add_argument("--run-id", default="loop", help="Run identifier")
    loop_parser.set_defaults(func=loop_run)

    subparsers.add_parser("status", help="Show current status").set_defaults(
        func=status
    )

    talk_parser = subparsers.add_parser("talk", help="Talk with the system")
    talk_parser.add_argument(
        "--provider",
        default=None,
        help="LLM provider to use (e.g. 'openai' or 'local')",
    )
    talk_parser.add_argument(
        "--prompt",
        default=None,
        help="If provided, generate a single response to the prompt and exit",
    )
    talk_parser.set_defaults(func=talk)

    quest_parser = subparsers.add_parser(
        "quest", help="Generate a skill from a specification"
    )
    quest_parser.add_argument("spec", type=Path, help="Path to specification JSON")
    quest_parser.set_defaults(func=quest)

    subparsers.add_parser("synthesize", help="Synthesize results").set_defaults(
        func=synthesize
    )
    report_parser = subparsers.add_parser(
        "report", help="Summarize performance from a run"
    )
    report_parser.add_argument("--id", required=True, help="Run identifier")
    report_parser.set_defaults(func=report)

    subparsers.add_parser("dashboard", help="Launch web dashboard").set_defaults(
        func=dashboard_run
    )

    args = parser.parse_args(argv)

    if args.home:
        os.environ["SINGULAR_HOME"] = str(args.home)

    if args.seed is not None:
        random.seed(args.seed)

    func: Command = args.func
    if args.command == "report":
        func(run_id=args.id)
    elif args.command == "talk":
        func(provider=args.provider, seed=args.seed, prompt=args.prompt)
    elif args.command == "loop":
        func(
            skills_dir=args.skills_dir,
            checkpoint=args.checkpoint,
            budget_seconds=args.budget_seconds,
            run_id=args.run_id,
            seed=args.seed,
        )
    elif args.command == "quest":
        func(spec=args.spec)
    elif args.command == "status":
        func()
    elif args.command == "spawn":
        func(
            parent_a=args.parent_a,
            parent_b=args.parent_b,
            out_dir=args.out_dir,
            seed=args.seed,
        )
    elif args.command in {"birth", "run"}:
        func(seed=args.seed)
    else:
        func()
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
