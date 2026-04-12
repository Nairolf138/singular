"""Command line interface for singular."""

from __future__ import annotations

import argparse
import getpass
import os
import random
import sys
import sysconfig
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Callable

__all__ = ["main"]


def _looks_like_dev_repo_root(path: Path) -> bool:
    """Heuristic to detect a development repository root."""

    return (path / "pyproject.toml").exists() and (path / "src" / "singular").is_dir()


def _in_path(target: Path, env_path: str | None = None) -> bool:
    """Return True when *target* is present in PATH."""

    path_value = env_path if env_path is not None else os.environ.get("PATH", "")
    target_norm = os.path.normcase(str(target.resolve()))
    for entry in path_value.split(os.pathsep):
        if not entry:
            continue
        try:
            entry_norm = os.path.normcase(str(Path(entry).resolve()))
        except OSError:
            entry_norm = os.path.normcase(entry)
        if entry_norm == target_norm:
            return True
    return False


def _normalize_windows_path_entry(entry: str) -> str:
    """Normalize a PATH entry for case-insensitive Windows comparisons."""

    return os.path.normcase(os.path.normpath(entry.strip().strip('"')))


def _doctor_fix_windows_user_path(scripts_path: Path) -> bool:
    """Add scripts_path to the Windows user Path variable when missing."""

    if os.name != "nt":
        print("⚠️ `doctor --fix` non supporté sur cette plateforme.")
        return False

    import winreg as _winreg

    winreg: Any = _winreg

    target = str(scripts_path)
    target_norm = _normalize_windows_path_entry(target)

    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        "Environment",
        0,
        winreg.KEY_READ | winreg.KEY_SET_VALUE,
    ) as key:
        try:
            raw_user_path, _ = winreg.QueryValueEx(key, "Path")
        except FileNotFoundError:
            raw_user_path = ""

        entries = [entry for entry in raw_user_path.split(";") if entry.strip()]
        deduped_entries: list[str] = []
        seen: set[str] = set()
        for entry in [*entries, target]:
            normalized = _normalize_windows_path_entry(entry)
            if not normalized or normalized in seen:
                continue
            deduped_entries.append(entry.strip())
            seen.add(normalized)

        if target_norm in {_normalize_windows_path_entry(entry) for entry in entries}:
            print("✅ Le dossier Scripts est déjà présent dans le Path utilisateur.")
            print("➡️ Pensez à redémarrer PowerShell pour recharger l'environnement.")
            return False

        new_user_path = ";".join(deduped_entries)
        winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, new_user_path)

    print("✅ Le dossier Scripts a été ajouté au Path utilisateur Windows.")
    print("➡️ Veuillez redémarrer PowerShell pour appliquer ce changement.")
    return True


def _doctor(*, fix: bool = False) -> None:
    """Display environment diagnostics for CLI installation."""

    python_executable = Path(sys.executable).resolve()
    scripts_path = Path(
        sysconfig.get_path("scripts", scheme=f"{os.name}_user")
    ).resolve()
    scripts_in_path = _in_path(scripts_path)

    try:
        installed_version = version("singular")
    except PackageNotFoundError:
        installed_version = "non installée (package introuvable)"

    print("Diagnostic Singular")
    print(f"- Python actif           : {python_executable}")
    print(f"- Scripts utilisateur    : {scripts_path}")
    print(f"- Scripts dans PATH      : {'oui' if scripts_in_path else 'non'}")
    print(f"- Version singular       : {installed_version}")

    if scripts_in_path:
        print("\n✅ PATH semble correctement configuré pour les scripts utilisateur.")
        return

    escaped_scripts = str(scripts_path).replace("'", "''")
    print("\n⚠️ Le dossier des scripts utilisateur n'est pas présent dans PATH.")
    print("Actions PowerShell (copier-coller) :")
    print(
        "[Environment]::SetEnvironmentVariable("
        "'Path', "
        "$env:Path + ';"
        f"{escaped_scripts}"
        "', "
        "'User'"
        ")"
    )
    print("$env:Path = [Environment]::GetEnvironmentVariable('Path', 'User')")
    print("Get-Command singular")
    print("singular --help")

    if fix:
        print("\nApplication du correctif automatique (`--fix`)…")
        _doctor_fix_windows_user_path(scripts_path)


def _mask_api_key(api_key: str) -> str:
    """Return a masked API key string safe for display."""

    if not api_key:
        return "(vide)"
    if len(api_key) <= 7:
        return "sk-****..."
    return f"{api_key[:3]}****...{api_key[-4:]}"


def _validate_openai_api_key(api_key: str) -> list[str]:
    """Return non-blocking validation warnings for an OpenAI API key."""

    warnings: list[str] = []
    if not api_key.strip():
        warnings.append("clé vide")
        return warnings
    if not api_key.startswith("sk-"):
        warnings.append("préfixe inattendu (attendu: sk-)")
    if len(api_key) < 12:
        warnings.append("longueur inhabituelle (très courte)")
    return warnings


def _set_windows_user_env_var(name: str, value: str) -> None:
    """Persist an environment variable in HKCU\\Environment on Windows."""

    import winreg as _winreg

    winreg: Any = _winreg
    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        "Environment",
        0,
        winreg.KEY_READ | winreg.KEY_SET_VALUE,
    ) as key:
        winreg.SetValueEx(key, name, 0, winreg.REG_EXPAND_SZ, value)


def _append_export_to_shell_profile(profile_path: Path, api_key: str) -> bool:
    """Append OPENAI_API_KEY export line to a shell profile (idempotent)."""

    profile = profile_path.expanduser()
    profile.parent.mkdir(parents=True, exist_ok=True)
    export_line = f"export OPENAI_API_KEY='{api_key}'"
    existing = profile.read_text(encoding="utf-8") if profile.exists() else ""
    if export_line in existing:
        print(f"✅ La configuration existe déjà dans {profile}.")
        return False
    with profile.open("a", encoding="utf-8") as handle:
        if existing and not existing.endswith("\n"):
            handle.write("\n")
        handle.write(f"{export_line}\n")
    print(f"✅ Variable OPENAI_API_KEY ajoutée à {profile}.")
    return True


def _configure_openai(api_key: str, *, shell_profile: str | None, test: bool) -> int:
    """Configure OPENAI_API_KEY for current platform and optionally test it."""

    warnings = _validate_openai_api_key(api_key)
    if "clé vide" in warnings:
        print("❌ Clé API vide: configuration annulée.", file=sys.stderr)
        return 1
    for warning in warnings:
        print(f"⚠️ Validation clé API: {warning}.")

    os.environ["OPENAI_API_KEY"] = api_key
    masked_key = _mask_api_key(api_key)
    print(f"✅ Clé OpenAI chargée (masquée): {masked_key}")

    if os.name == "nt":
        _set_windows_user_env_var("OPENAI_API_KEY", api_key)
        print("✅ OPENAI_API_KEY enregistrée dans HKCU\\Environment.")
        print("➡️ Veuillez redémarrer PowerShell pour recharger l'environnement.")
    else:
        if shell_profile:
            profile_path = Path(shell_profile)
            answer = input(
                f"Confirmer l'écriture dans {profile_path.expanduser()} ? "
                "Tapez OUI pour confirmer: "
            )
            if answer.strip() == "OUI":
                _append_export_to_shell_profile(profile_path, api_key)
                print("➡️ Ouvrez un nouveau shell (ou `source` le profil) pour appliquer.")
            else:
                print("Écriture annulée. Aucune persistance shell effectuée.")
        else:
            print("Pour persister la clé sur Linux/macOS, ajoutez à votre profil shell:")
            print("export OPENAI_API_KEY='sk-...'")

    if test:
        from .providers import llm_openai

        reply = llm_openai.generate_reply("Reply with: ok")
        if reply in {
            "OpenAI API key not configured.",
            "Error communicating with OpenAI.",
        }:
            print(f"❌ Test OpenAI échoué: {reply}")
            return 1
        print("✅ Test OpenAI réussi (provider joignable).")
    return 0


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

    from .lives import (
        bootstrap_life,
        delete_life,
        get_registry_root,
        load_registry,
        resolve_life,
        uninstall_singular,
    )

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
    loop_parser.add_argument("--budget-seconds", type=float, required=False)
    loop_parser.add_argument(
        "--ticks",
        type=int,
        default=None,
        help=(
            "Legacy alias from older tick-based syntax. "
            "Use --budget-seconds instead."
        ),
    )
    loop_parser.add_argument("--run-id", default="loop", help="Run identifier")

    status_parser = subparsers.add_parser("status", help="Show current status")
    status_parser.add_argument(
        "--verbose",
        action="store_true",
        help="Display detailed alerts and diagnostics",
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
    doctor_parser = subparsers.add_parser(
        "doctor", help="Diagnose CLI installation and PATH"
    )
    doctor_parser.add_argument(
        "--fix",
        action="store_true",
        help="Try to add user Scripts directory to user Path on Windows",
    )
    config_parser = subparsers.add_parser("config", help="Configure providers and env")
    config_subparsers = config_parser.add_subparsers(
        dest="config_command", required=True
    )
    config_openai_parser = config_subparsers.add_parser(
        "openai", help="Configure OPENAI_API_KEY"
    )
    config_openai_parser.add_argument(
        "--api-key",
        default=None,
        help="OpenAI API key (non-interactive mode, useful in CI)",
    )
    config_openai_parser.add_argument(
        "--shell-profile",
        default=None,
        help="Shell profile path to append export (e.g. ~/.bashrc or ~/.zshrc)",
    )
    config_openai_parser.add_argument(
        "--test",
        action="store_true",
        help="Run a short provider ping after configuration",
    )

    lives_parser = subparsers.add_parser("lives", help="Manage lives")
    lives_subparsers = lives_parser.add_subparsers(dest="lives_command", required=True)
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

    ecosystem_parser = subparsers.add_parser(
        "ecosystem", help="Run multiple lives in a shared ecosystem"
    )
    ecosystem_subparsers = ecosystem_parser.add_subparsers(
        dest="ecosystem_command", required=True
    )
    ecosystem_run = ecosystem_subparsers.add_parser(
        "run", help="Execute an ecosystem loop across multiple lives"
    )
    ecosystem_run.add_argument(
        "--life",
        dest="ecosystem_lives",
        action="append",
        default=[],
        help="Life slug/name to include (repeatable)",
    )
    ecosystem_run.add_argument(
        "--life-group",
        dest="ecosystem_groups",
        action="append",
        default=[],
        help="Comma-separated list of life slugs/names",
    )
    ecosystem_run.add_argument("--checkpoint", type=Path, default=None)
    ecosystem_run.add_argument("--budget-seconds", type=float, required=True)
    ecosystem_run.add_argument("--run-id", default="ecosystem", help="Run identifier")

    uninstall_parser = subparsers.add_parser(
        "uninstall", help="Remove Singular data from SINGULAR_ROOT"
    )
    uninstall_mode_group = uninstall_parser.add_mutually_exclusive_group(required=True)
    uninstall_mode_group.add_argument(
        "--keep-lives",
        action="store_true",
        help="Remove only global technical artefacts (mem/, runs/)",
    )
    uninstall_mode_group.add_argument(
        "--purge-lives",
        action="store_true",
        help="Remove all Singular data (lives/, mem/, runs/)",
    )
    uninstall_parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip confirmation prompt",
    )
    uninstall_parser.add_argument(
        "--force",
        action="store_true",
        help="Allow purge even if root looks like a development repository",
    )

    args = parser.parse_args(argv_list)

    if args.command == "loop":
        if args.budget_seconds is None and args.ticks is not None:
            parser.error(
                "`--ticks` n'est plus accepté seul. "
                "Utilisez `singular loop --budget-seconds <secondes>` "
                "(conversion legacy: 1 tick ≈ 1 seconde)."
            )
        if args.budget_seconds is None:
            parser.error(
                "argument requis: --budget-seconds "
                "(exemple: `singular loop --budget-seconds 10`)."
            )

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
        from .organisms.spawn import spawn

        spawn(
            parent_a=args.parent_a,
            parent_b=args.parent_b,
            out_dir=args.out_dir,
            seed=args.seed,
        )

    elif args.command == "run":
        from .runs.run import run as run_run

        _ensure_active_life(resolve_life, args.life)
        run_run(seed=args.seed)

    elif args.command == "loop":
        from .runs.loop import loop as loop_run

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

    elif args.command == "ecosystem":
        from .runs.loop import loop as loop_run

        if args.ecosystem_command != "run":
            raise SystemExit(f"Sous-commande ecosystem inconnue: {args.ecosystem_command}")

        names = list(args.ecosystem_lives)
        for group in args.ecosystem_groups:
            names.extend(part.strip() for part in group.split(",") if part.strip())

        if not names:
            raise SystemExit(
                "Aucune vie fournie. Utilisez --life (multiple) ou --life-group."
            )

        organisms: dict[str, Path] = {}
        for life_name in names:
            life_dir = resolve_life(life_name)
            if life_dir is None:
                raise SystemExit(f"Vie introuvable: {life_name}")
            organisms[life_name] = life_dir / "skills"

        root = get_registry_root()
        checkpoint = args.checkpoint or (root / "runs" / "ecosystem_checkpoint.json")
        loop_run(
            skills_dirs=organisms,
            checkpoint=checkpoint,
            budget_seconds=args.budget_seconds,
            run_id=args.run_id,
            seed=args.seed,
        )

    elif args.command == "status":
        from .organisms.status import status

        _ensure_active_life(resolve_life, args.life)
        status(verbose=args.verbose)

    elif args.command == "talk":
        from .organisms.talk import talk

        _ensure_active_life(resolve_life, args.life)
        talk(provider=args.provider, seed=args.seed, prompt=args.prompt)

    elif args.command == "quest":
        from .organisms.quest import quest

        _ensure_active_life(resolve_life, args.life)
        quest(spec=args.spec)

    elif args.command == "synthesize":
        from .runs.synthesize import synthesize

        _ensure_active_life(resolve_life, args.life)
        synthesize(args.code)

    elif args.command == "report":
        from .runs.report import report

        report(run_id=args.id)

    elif args.command == "dashboard":
        _ensure_active_life(resolve_life, args.life)
        from .dashboard import run as dashboard_run

        dashboard_run()

    elif args.command == "doctor":
        _doctor(fix=args.fix)

    elif args.command == "config":
        if args.config_command == "openai":
            api_key = (
                args.api_key
                if args.api_key is not None
                else getpass.getpass("OpenAI API key (input hidden): ").strip()
            )
            return _configure_openai(
                api_key,
                shell_profile=args.shell_profile,
                test=args.test,
            )

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
            print(f"Vie créée: {metadata.name} ({metadata.slug}) → {metadata.path}")
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
            print(f"Vie supprimée: {metadata.name} ({metadata.slug})")
            next_life = resolve_life(None)
            if next_life is not None:
                os.environ["SINGULAR_HOME"] = str(next_life)
            else:
                os.environ.pop("SINGULAR_HOME", None)

    elif args.command == "uninstall":
        purge_lives = bool(args.purge_lives)
        root = get_registry_root()
        if purge_lives and _looks_like_dev_repo_root(root) and not args.force:
            print(
                "Refus de purge: le root cible ressemble au repo de développement "
                f"('{root}'). Utilisez --force pour confirmer explicitement.",
                file=sys.stderr,
            )
            return 1

        if purge_lives and not args.yes:
            confirmation = input(
                "⚠️ PURGE COMPLÈTE demandée.\n"
                f"Chemin cible : {root}\n"
                "Cette action supprimera définitivement lives/, mem/ et runs/.\n"
                "Tapez 'PURGE' pour confirmer: "
            )
            if confirmation.strip() != "PURGE":
                print("Désinstallation annulée.")
                return 0
        try:
            uninstall_singular(purge_lives=purge_lives)
        except PermissionError as exc:
            print(
                f"Erreur: permissions insuffisantes pour supprimer '{exc.filename or root}'.",
                file=sys.stderr,
            )
            return 1
        except OSError as exc:
            print(
                f"Erreur lors de la désinstallation: {exc}",
                file=sys.stderr,
            )
            return 1

        if purge_lives:
            print(f"Données Singular supprimées sous: {root}")
        else:
            print(f"Artefacts globaux supprimés sous: {root} (mem/, runs/)")

    else:  # pragma: no cover - defensive programming
        raise SystemExit(f"Commande inconnue: {args.command}")

    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
