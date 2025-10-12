"""Command line interface for singular."""

from __future__ import annotations

import argparse
import os
import random
from pathlib import Path
from typing import Callable

__all__ = ["main"]


def _preparse_environment(argv: list[str] | None) -> argparse.Namespace:
    """Parse minimal options to configure the environment before imports."""

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--home", type=Path)
    parser.add_argument("--life")
    args, _ = parser.parse_known_args(argv)

    if args.root:
        os.environ["SINGULAR_ROOT"] = str(args.root)
    if args.home:
        os.environ["SINGULAR_HOME"] = str(args.home)

    from . import lives as life_module

    life_name = args.life
    needs_resolution = life_name is not None or (
        args.home is None and "SINGULAR_HOME" not in os.environ
    )
    if needs_resolution:
        life_dir = life_module.resolve_life(life_name)
        if life_dir is not None:
            os.environ["SINGULAR_HOME"] = str(life_dir)

    return args


def _ensure_active_life(
    resolve: Callable[[str | None], Path | None], life_name: str | None
) -> Path:
    """Ensure a life is active and return its directory."""

    life_dir = resolve(life_name)
    if life_dir is None:
        raise SystemExit(
            "Aucune vie active. Utilisez `singular birth --name ...` ou "
            "`singular lives create` pour créer une vie."
        )
    os.environ["SINGULAR_HOME"] = str(life_dir)
    return life_dir


def main(argv: list[str] | None = None) -> int:
    """Run the singular command line interface."""

    argv_list = list(argv) if argv is not None else None
    _preparse_environment(argv_list)

    from .lives import bootstrap_life, delete_life, load_registry, resolve_life
    from .organisms.quest import quest
    from .organisms.spawn import spawn
    from .organisms.status import status
    from .organisms.talk import talk
    from .runs.loop import loop as loop_run
    from .runs.report import report
    from .runs.run import run as run_run
    from .runs.synthesize import synthesize
    from .dashboard import run as dashboard_run

    parser = argparse.ArgumentParser(prog="singular")
    parser.add_argument(
        "--seed", type=int, default=None, help="Random seed for reproducibility"
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=os.environ.get("SINGULAR_ROOT"),
        help="Base directory storing lives (env: SINGULAR_ROOT)",
    )
    parser.add_argument(
        "--home",
        type=Path,
        default=os.environ.get("SINGULAR_HOME"),
        help="Override life directory (env: SINGULAR_HOME)",
    )
    parser.add_argument(
        "--life",
        default=None,
        help="Name or slug of the life to activate",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    birth_parser = subparsers.add_parser("birth", help="Birth a new life")
    birth_parser.add_argument(
        "--name",
        default="New life",
        help="Human readable name for the life",
    )

    spawn_parser = subparsers.add_parser(
        "spawn", help="Create child organism from two parents"
    )
    spawn_parser.add_argument("parent_a", type=Path)
    spawn_parser.add_argument("parent_b", type=Path)
    spawn_parser.add_argument("--out-dir", type=Path, default=None)

    subparsers.add_parser("run", help="Execute a run")

    loop_parser = subparsers.add_parser("loop", help="Execute evolutionary loop")
    loop_parser.add_argument("--skills-dir", type=Path, default=None)
    loop_parser.add_argument("--checkpoint", type=Path, default=None)
    loop_parser.add_argument("--budget-seconds", type=float, required=True)
    loop_parser.add_argument("--run-id", default="loop", help="Run identifier")

    subparsers.add_parser("status", help="Show current status")

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

    quest_parser = subparsers.add_parser(
        "quest", help="Generate a skill from a specification"
    )
    quest_parser.add_argument("spec", type=Path, help="Path to specification JSON")

    synth_parser = subparsers.add_parser("synthesize", help="Synthesize results")
    synth_parser.add_argument("code", help="Code snippet to store in memory")

    report_parser = subparsers.add_parser(
        "report", help="Summarize performance from a run"
    )
    report_parser.add_argument("--id", required=True, help="Run identifier")

    subparsers.add_parser("dashboard", help="Launch web dashboard")

    lives_parser = subparsers.add_parser("lives", help="Manage lives")
    lives_subparsers = lives_parser.add_subparsers(
        dest="lives_command", required=True
    )
    lives_subparsers.add_parser("list", help="List registered lives")
    lives_create = lives_subparsers.add_parser("create", help="Create a new life")
    lives_create.add_argument(
        "--name",
        default="New life",
        help="Human readable name for the life",
    )
    lives_use = lives_subparsers.add_parser("use", help="Activate an existing life")
    lives_use.add_argument("name", help="Slug or name of the life to activate")
    lives_delete = lives_subparsers.add_parser(
        "delete", help="Delete a life and its data"
    )
    lives_delete.add_argument("name", help="Slug or name of the life to delete")

    args = parser.parse_args(argv_list)

    if args.root:
        os.environ["SINGULAR_ROOT"] = str(args.root)

    if args.life:
        life_dir = resolve_life(args.life)
        if life_dir is None:
            raise SystemExit(f"Vie introuvable: {args.life}")
        os.environ["SINGULAR_HOME"] = str(life_dir)
    elif args.home:
        os.environ["SINGULAR_HOME"] = str(args.home)

    if args.seed is not None:
        random.seed(args.seed)

    if args.command == "birth":
        name = args.name or "New life"
        metadata = bootstrap_life(name, seed=args.seed)
        os.environ["SINGULAR_HOME"] = str(metadata.path)
        print(f"Vie créée: {metadata.name} ({metadata.slug}) → {metadata.path}")

    elif args.command == "spawn":
        spawn(
            parent_a=args.parent_a,
            parent_b=args.parent_b,
            out_dir=args.out_dir,
            seed=args.seed,
        )

    elif args.command == "run":
        _ensure_active_life(resolve_life, args.life)
        run_run(seed=args.seed)

    elif args.command == "loop":
        life_dir = _ensure_active_life(resolve_life, args.life)
        skills_dir = args.skills_dir or life_dir / "skills"
        checkpoint = args.checkpoint or life_dir / "life_checkpoint.json"
        loop_run(
            skills_dir=skills_dir,
            checkpoint=checkpoint,
            budget_seconds=args.budget_seconds,
            run_id=args.run_id,
            seed=args.seed,
        )

    elif args.command == "status":
        _ensure_active_life(resolve_life, args.life)
        status()

    elif args.command == "talk":
        _ensure_active_life(resolve_life, args.life)
        talk(provider=args.provider, seed=args.seed, prompt=args.prompt)

    elif args.command == "quest":
        _ensure_active_life(resolve_life, args.life)
        quest(spec=args.spec)

    elif args.command == "synthesize":
        _ensure_active_life(resolve_life, args.life)
        synthesize(args.code)

    elif args.command == "report":
        report(run_id=args.id)

    elif args.command == "dashboard":
        _ensure_active_life(resolve_life, args.life)
        dashboard_run()

    elif args.command == "lives":
        if args.lives_command == "list":
            registry = load_registry()
            lives = registry.get("lives", {})
            if not lives:
                print("Aucune vie enregistrée.")
            else:
                active = registry.get("active")
                for slug, meta in sorted(lives.items()):
                    marker = "*" if slug == active else " "
                    print(
                        f"{marker} {meta.name} [{slug}] - {meta.path}"
                        f" (créée le {meta.created_at})"
                    )
        elif args.lives_command == "create":
            name = args.name or "New life"
            metadata = bootstrap_life(name, seed=args.seed)
            os.environ["SINGULAR_HOME"] = str(metadata.path)
            print(
                f"Vie créée: {metadata.name} ({metadata.slug}) → {metadata.path}"
            )
        elif args.lives_command == "use":
            life_dir = resolve_life(args.name)
            if life_dir is None:
                raise SystemExit(f"Vie introuvable: {args.name}")
            os.environ["SINGULAR_HOME"] = str(life_dir)
            print(f"Vie active: {args.name} → {life_dir}")
        elif args.lives_command == "delete":
            try:
                metadata = delete_life(args.name)
            except KeyError as exc:
                raise SystemExit(f"Vie introuvable: {args.name}") from exc
            print(
                f"Vie supprimée: {metadata.name} ({metadata.slug})"
            )
            next_life = resolve_life(None)
            if next_life is not None:
                os.environ["SINGULAR_HOME"] = str(next_life)
            else:
                os.environ.pop("SINGULAR_HOME", None)

    else:  # pragma: no cover - defensive programming
        raise SystemExit(f"Commande inconnue: {args.command}")

    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
