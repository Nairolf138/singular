"""Command line interface for singular."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import random
import re
import sys
import sysconfig
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Callable

__all__ = ["main"]


def _bounded_trait_value(raw: str) -> float:
    """Parse a psyche trait override constrained to ``[0, 1]``."""

    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError("doit être un nombre entre 0 et 1") from exc
    if value < 0.0 or value > 1.0:
        raise argparse.ArgumentTypeError("doit être compris entre 0 et 1")
    return value


def _extract_talk_life_alias(argv: list[str] | None) -> str | None:
    """Extract ``talk --life/--live`` value from raw argv when present."""

    if not argv:
        return None

    try:
        talk_index = argv.index("talk")
    except ValueError:
        return None

    tokens = argv[talk_index + 1 :]
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token in {"--life", "--live"} and index + 1 < len(tokens):
            return tokens[index + 1]
        if token.startswith("--life="):
            return token.split("=", 1)[1]
        if token.startswith("--live="):
            return token.split("=", 1)[1]
        index += 1
    return None


def _build_life_suggestion_message(unknown: str) -> str | None:
    """Return a targeted suggestion when an unknown argument looks like a life slug."""

    if not unknown.startswith("--"):
        return None
    candidate = unknown[2:].strip()
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]*", candidate):
        return None
    return (
        f"Argument inconnu `{unknown}`. "
        "Si c'est un nom de vie, utilisez explicitement : "
        "`singular --life <slug> talk` "
        "ou `singular --root <root> --life <slug> talk`."
    )


def _suggest_life_flag_for_unknown_args(argv: list[str] | None) -> str | None:
    """Inspect argv and suggest ``--life`` when unknown options look like slugs."""

    if not argv:
        return None

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--seed")
    parser.add_argument("--root")
    parser.add_argument("--home")
    parser.add_argument("--life")
    parser.add_argument("--format")
    subparsers = parser.add_subparsers(dest="command")
    talk_parser = subparsers.add_parser("talk", add_help=False)
    talk_parser.add_argument("--provider")
    talk_parser.add_argument("--prompt")
    talk_parser.add_argument("--life")
    talk_parser.add_argument("--live")

    try:
        _, unknown = parser.parse_known_args(argv)
    except SystemExit:
        return None

    for token in unknown:
        message = _build_life_suggestion_message(token)
        if message is not None:
            return message
    return None

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


_POLICY_SETTERS: dict[str, tuple[str, str]] = {
    "memory.preserve_threshold": ("float", "memory_preserve_threshold"),
    "forgetting.enabled": ("bool", "forgetting_enabled"),
    "forgetting.max_episodic_entries": ("int", "forgetting_max_episodic_entries"),
    "autonomy.safe_mode": ("bool", "safe_mode"),
    "autonomy.mutation_quota_per_window": ("int", "mutation_quota_per_window"),
    "autonomy.mutation_quota_window_seconds": ("float", "mutation_quota_window_seconds"),
    "autonomy.runtime_call_quota_per_hour": ("int", "runtime_call_quota_per_hour"),
    "autonomy.runtime_blacklisted_capabilities": ("strings", "runtime_blacklisted_capabilities"),
    "autonomy.auto_rollback_failure_threshold": ("int", "auto_rollback_failure_threshold"),
    "autonomy.auto_rollback_cost_threshold": ("float", "auto_rollback_cost_threshold"),
    "autonomy.safe_mode_review_required_skill_families": (
        "strings",
        "safe_mode_review_required_skill_families",
    ),
    "autonomy.circuit_breaker_threshold": ("int", "circuit_breaker_threshold"),
    "autonomy.circuit_breaker_window_seconds": ("float", "circuit_breaker_window_seconds"),
    "autonomy.circuit_breaker_cooldown_seconds": ("float", "circuit_breaker_cooldown_seconds"),
    "autonomy.skill_circuit_breaker_failure_threshold": ("int", "skill_circuit_breaker_failure_threshold"),
    "autonomy.skill_circuit_breaker_cost_threshold": ("float", "skill_circuit_breaker_cost_threshold"),
    "autonomy.skill_circuit_breaker_cooldown_seconds": ("float", "skill_circuit_breaker_cooldown_seconds"),
    "permissions.modifiable_paths": ("paths", "modifiable_paths"),
    "permissions.review_required_paths": ("paths", "review_required_paths"),
    "permissions.forbidden_paths": ("paths", "forbidden_paths"),
    "permissions.force_allow_paths": ("paths", "force_allow_paths"),
}


def _parse_policy_value(expected_type: str, raw: str) -> object:
    value = raw.strip()
    if expected_type == "bool":
        lowered = value.lower()
        if lowered in {"true", "1", "yes", "oui"}:
            return True
        if lowered in {"false", "0", "no", "non"}:
            return False
        raise ValueError("expected boolean value (true/false)")
    if expected_type == "int":
        return int(value)
    if expected_type == "float":
        return float(value)
    if expected_type == "paths":
        if not value:
            return tuple()
        parts = [part.strip().strip("/") for part in value.split(",")]
        if any(not part for part in parts):
            raise ValueError("empty path entry is not allowed")
        return tuple(parts)
    if expected_type == "strings":
        if not value:
            return tuple()
        parts = [part.strip() for part in value.split(",")]
        if any(not part for part in parts):
            raise ValueError("empty entry is not allowed")
        return tuple(parts)
    raise ValueError(f"unsupported policy type: {expected_type}")


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

    life_name = _extract_talk_life_alias(argv) or args.life
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


def _resolve_latest_run_id(runs_root: Path | None = None) -> str | None:
    """Return the most recent run identifier from ``runs/``."""

    base = Path(runs_root or Path(os.environ.get("SINGULAR_HOME", ".")) / "runs")
    if not base.exists():
        return None

    latest: tuple[float, str] | None = None

    for run_dir in base.iterdir():
        if not run_dir.is_dir():
            continue
        events_path = run_dir / "events.jsonl"
        if not events_path.exists():
            continue
        candidate = (events_path.stat().st_mtime, run_dir.name)
        if latest is None or candidate[0] > latest[0]:
            latest = candidate

    for legacy_log in base.glob("*.jsonl"):
        stem = legacy_log.stem
        run_id = stem.rsplit("-", 1)[0] if "-" in stem else stem
        candidate = (legacy_log.stat().st_mtime, run_id)
        if latest is None or candidate[0] > latest[0]:
            latest = candidate

    return latest[1] if latest is not None else None


def _can_prompt() -> bool:
    """Return True when guided prompts can safely run."""

    return bool(getattr(sys.stdin, "isatty", lambda: False)())


def _prompt_text(prompt: str, default: str) -> str:
    """Prompt for text with a default value."""

    answer = input(f"{prompt} [{default}] : ").strip()
    return answer or default


def _prompt_yes_no(prompt: str, *, default: bool = True) -> bool:
    """Prompt a yes/no question and return the selected boolean."""

    default_hint = "O/n" if default else "o/N"
    answer = input(f"{prompt} ({default_hint}) : ").strip().lower()
    if not answer:
        return default
    return answer in {"o", "oui", "y", "yes"}


def _print_table(headers: list[str], rows: list[list[str]]) -> None:
    """Render a minimal fixed-width table."""

    if not rows:
        return
    widths = [len(header) for header in headers]
    for row in rows:
        for idx, cell in enumerate(row):
            widths[idx] = max(widths[idx], len(cell))
    def _fmt(row: list[str]) -> str:
        return " | ".join(cell.ljust(widths[idx]) for idx, cell in enumerate(row))
    print(_fmt(headers))
    print("-+-".join("-" * width for width in widths))
    for row in rows:
        print(_fmt(row))


def _implicit_registry_root_from_env_or_default() -> Path:
    """Return the implicit registry root used before any ``--root`` override."""

    raw = os.environ.get("SINGULAR_ROOT")
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".singular"


def _print_registry_context_message_if_needed(
    selected_root: Path | None, *, previous_root: Path
) -> None:
    """Inform the user when ``--root`` switches to another registry context."""

    if selected_root is None:
        return

    active_root = selected_root.expanduser().resolve()
    if active_root == previous_root:
        return

    print(
        "Vous utilisez un autre registre de vies: "
        f"{active_root} (au lieu de {previous_root})."
    )


def main(argv: list[str] | None = None) -> int:
    """Run the singular command line interface."""

    implicit_root_before_override = _implicit_registry_root_from_env_or_default().resolve()
    argv_list = list(argv) if argv is not None else None
    _preparse_environment(argv_list)

    from .lives import (
        ally_lives,
        archive_life,
        bootstrap_life,
        clone_life,
        delete_life,
        get_registry_root,
        list_relations,
        load_registry,
        memorialize_life,
        reconcile_lives,
        resolve_life,
        rival_lives,
        set_proximity,
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
        help=(
            "Base directory storing lives (env: SINGULAR_ROOT). "
            "Un message d'information est affiché si ce root diffère du contexte implicite."
        ),
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
    parser.add_argument(
        "--format",
        dest="output_format",
        choices=("table", "json", "plain"),
        default="plain",
        help="Output format for compatible commands",
    )
    parser.add_argument(
        "--safe-mode",
        action="store_true",
        help="Active un mode global qui bloque les mutations autonomes",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    birth_parser = subparsers.add_parser(
        "birth",
        help="Birth a new life (affiche aussi le root de registre utilisé)",
    )
    birth_parser.add_argument(
        "--name",
        default="New life",
        help="Human readable name for the life",
    )
    birth_parser.add_argument(
        "--curiosity",
        type=_bounded_trait_value,
        default=None,
        help="Trait initial borné dans [0,1]",
    )
    birth_parser.add_argument(
        "--patience",
        type=_bounded_trait_value,
        default=None,
        help="Trait initial borné dans [0,1]",
    )
    birth_parser.add_argument(
        "--playfulness",
        type=_bounded_trait_value,
        default=None,
        help="Trait initial borné dans [0,1]",
    )
    birth_parser.add_argument(
        "--optimism",
        type=_bounded_trait_value,
        default=None,
        help="Trait initial borné dans [0,1]",
    )
    birth_parser.add_argument(
        "--resilience",
        type=_bounded_trait_value,
        default=None,
        help="Trait initial borné dans [0,1]",
    )
    birth_parser.add_argument(
        "--starter-profile",
        default="minimal",
        help="Profil de starter skills à appliquer (ex: minimal, assistant, ops, creative)",
    )
    birth_parser.add_argument(
        "--starter-skill",
        action="append",
        default=[],
        help="Skill starter individuel à ajouter (option répétable)",
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
    status_parser.add_argument(
        "--format",
        dest="status_output_format",
        choices=("table", "json", "plain"),
        default=None,
        help="Output format for the status command",
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
    talk_parser.add_argument(
        "--life",
        dest="talk_life",
        default=None,
        help="Life slug/name for `talk` (prioritaire sur l'option globale)",
    )
    talk_parser.add_argument(
        "--live",
        dest="talk_life_legacy",
        default=None,
        help="Alias de compatibilité déprécié pour `talk --life`",
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
    report_parser.add_argument("--id", required=False, default=None, help="Run identifier")
    report_parser.add_argument(
        "--format",
        dest="report_output_format",
        choices=("table", "json", "plain"),
        default=None,
        help="Output format for the report command",
    )
    report_parser.add_argument(
        "--export",
        default=None,
        help="Export report to file (.json/.md) or use `markdown` for stdout",
    )
    rollback_parser = subparsers.add_parser(
        "rollback", help="Rollback atomique vers une génération stable"
    )
    rollback_parser.add_argument(
        "--generation",
        type=int,
        required=True,
        help="Identifiant de génération à restaurer",
    )

    subparsers.add_parser("dashboard", help="Launch web dashboard")
    quickstart_parser = subparsers.add_parser(
        "quickstart", help="Guided setup to create and activate a life"
    )
    quickstart_parser.add_argument(
        "--name",
        default=None,
        help="Life name (if omitted, a guided prompt is shown)",
    )
    monitor_parser = subparsers.add_parser("monitor", help="Guided status monitoring")
    monitor_parser.add_argument(
        "--verbose",
        action="store_true",
        help="Display detailed alerts and diagnostics",
    )
    watch_parser = subparsers.add_parser(
        "watch",
        aliases=["veille"],
        help="Lance une veille continue avec détection de changements significatifs",
    )
    watch_parser.add_argument(
        "--interval",
        type=float,
        default=5.0,
        help="Intervalle en secondes entre deux perceptions",
    )
    watch_parser.add_argument(
        "--sources",
        default="file,weather,runs,folder",
        help="Sources surveillées (CSV): file,weather,runs,folder",
    )
    watch_parser.add_argument(
        "--cpu-budget",
        type=float,
        default=50.0,
        help="Budget CPU (%) informatif pour l'orchestration de veille",
    )
    watch_parser.add_argument(
        "--memory-budget",
        type=float,
        default=512.0,
        help="Budget mémoire (MB) informatif pour l'orchestration de veille",
    )
    watch_parser.add_argument(
        "--watch-dir",
        type=Path,
        default=None,
        help="Dossier supplémentaire à surveiller",
    )
    watch_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Détecte et émet les événements sans persister l'inbox",
    )
    orchestrate_parser = subparsers.add_parser(
        "orchestrate",
        help="Pilote un cycle structuré (veille/action/introspection/sommeil)",
    )
    orchestrate_subparsers = orchestrate_parser.add_subparsers(
        dest="orchestrate_command",
        required=True,
    )
    orchestrate_run = orchestrate_subparsers.add_parser(
        "run",
        help="Lance le daemon d'orchestration structuré",
    )
    orchestrate_run.add_argument("--veille-seconds", type=float, default=None)
    orchestrate_run.add_argument("--action-seconds", type=float, default=None)
    orchestrate_run.add_argument("--introspection-seconds", type=float, default=None)
    orchestrate_run.add_argument("--sommeil-seconds", type=float, default=None)
    orchestrate_run.add_argument("--poll-interval", type=float, default=None)
    orchestrate_run.add_argument("--tick-budget", type=float, default=None)
    orchestrate_run.add_argument(
        "--lifecycle-config",
        default=None,
        help="Chemin vers le fichier lifecycle.yaml pour l'horloge vitale",
    )
    orchestrate_run.add_argument(
        "--dry-run",
        action="store_true",
        help="Active les phases sans exécuter la mutation",
    )
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
    lives_archive = lives_subparsers.add_parser(
        "archive", help="Archive a life (status extinct) with guided next steps"
    )
    lives_archive.add_argument("name", help="Slug or name of the life to archive")
    lives_memorial = lives_subparsers.add_parser(
        "memorial", help="Write a memorial message for a life"
    )
    lives_memorial.add_argument("name", help="Slug or name of the life")
    lives_memorial.add_argument(
        "--message",
        default="Merci pour ce cycle de vie.",
        help="Message à inscrire dans le mémorial",
    )
    lives_clone = lives_subparsers.add_parser(
        "clone", help="Clone a life to a new life with guided next steps"
    )
    lives_clone.add_argument("name", help="Slug or name of the source life")
    lives_clone.add_argument("--new-name", default=None, help="Nom de la nouvelle vie")
    lives_relations = lives_subparsers.add_parser("relations", help="Afficher relations d'une vie")
    lives_relations.add_argument("--name", default=None, help="Vie ciblée (sinon vie active)")
    lives_ally = lives_subparsers.add_parser("ally", help="Déclarer deux vies alliées")
    lives_ally.add_argument("name", help="Vie source")
    lives_ally.add_argument("other", help="Vie alliée")
    lives_rival = lives_subparsers.add_parser("rival", help="Déclarer deux vies rivales")
    lives_rival.add_argument("name", help="Vie source")
    lives_rival.add_argument("other", help="Vie rivale")
    lives_reconcile = lives_subparsers.add_parser("reconcile", help="Réconcilier deux vies")
    lives_reconcile.add_argument("name", help="Vie source")
    lives_reconcile.add_argument("other", help="Vie à réconcilier")
    lives_proximity = lives_subparsers.add_parser("proximity", help="Ajuster score proximité")
    lives_proximity.add_argument("name", help="Vie ciblée")
    lives_proximity.add_argument("--score", type=float, required=True, help="Score [0..1]")

    values_parser = subparsers.add_parser("values", help="Inspecter les poids de valeurs")
    values_subparsers = values_parser.add_subparsers(dest="values_command", required=True)
    values_subparsers.add_parser("show", help="Afficher la configuration des valeurs chargée")

    policy_parser = subparsers.add_parser(
        "policy", help="Inspecter et modifier la politique globale"
    )
    policy_subparsers = policy_parser.add_subparsers(dest="policy_command", required=True)
    policy_subparsers.add_parser("show", help="Afficher la politique active")
    policy_set_parser = policy_subparsers.add_parser(
        "set",
        help="Modifier une clé de politique (validation stricte)",
    )
    policy_set_parser.add_argument("--key", required=True, choices=tuple(sorted(_POLICY_SETTERS.keys())))
    policy_set_parser.add_argument("--value", required=True, help="Nouvelle valeur")

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

    beliefs_parser = subparsers.add_parser("beliefs", help="Audit and reset beliefs")
    beliefs_subparsers = beliefs_parser.add_subparsers(
        dest="beliefs_command", required=True
    )
    beliefs_audit = beliefs_subparsers.add_parser(
        "audit", help="Inspect current beliefs"
    )
    beliefs_audit.add_argument(
        "--limit",
        type=int,
        default=25,
        help="Maximum number of beliefs to display",
    )
    beliefs_reset = beliefs_subparsers.add_parser(
        "reset", help="Reset beliefs (targeted or all)"
    )
    reset_mode = beliefs_reset.add_mutually_exclusive_group(required=True)
    reset_mode.add_argument("--hypothesis", default=None, help="Exact hypothesis key")
    reset_mode.add_argument("--prefix", default=None, help="Delete by key prefix")
    reset_mode.add_argument(
        "--all",
        action="store_true",
        help="Delete all beliefs",
    )

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

    try:
        args = parser.parse_args(argv_list)
    except SystemExit as exc:
        if exc.code == 2:
            suggestion = _suggest_life_flag_for_unknown_args(argv_list)
            if suggestion is not None:
                print(suggestion, file=sys.stderr)
        raise

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

    if args.command == "talk":
        selected_life = args.talk_life
        if args.talk_life_legacy is not None:
            print(
                "⚠️ `talk --live` est déprécié. Utilisez `talk --life`.",
                file=sys.stderr,
            )
            if selected_life is None:
                selected_life = args.talk_life_legacy
        args.life = selected_life if selected_life is not None else args.life

    _print_registry_context_message_if_needed(
        args.root,
        previous_root=implicit_root_before_override,
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
    if args.safe_mode:
        os.environ["SINGULAR_SAFE_MODE"] = "1"

    if args.command == "birth":
        psyche_overrides = {
            trait: getattr(args, trait)
            for trait in (
                "curiosity",
                "patience",
                "playfulness",
                "optimism",
                "resilience",
            )
            if getattr(args, trait, None) is not None
        }
        name = args.name or "New life"
        metadata = bootstrap_life(
            name,
            seed=args.seed,
            psyche_overrides=psyche_overrides or None,
            starter_profile=args.starter_profile,
            starter_skills=args.starter_skill,
        )
        registry_root = get_registry_root()
        os.environ["SINGULAR_HOME"] = str(metadata.path)
        print(f"Vie créée: {metadata.name} ({metadata.slug}) → {metadata.path}")
        print(f"Registre de vies utilisé: {registry_root}")

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
            safe_mode=args.safe_mode,
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
            safe_mode=args.safe_mode,
        )

    elif args.command == "status":
        from .organisms.status import status

        _ensure_active_life(resolve_life, args.life)
        status_format = args.status_output_format or args.output_format
        status(verbose=args.verbose, output_format=status_format)

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

        run_id = args.id or _resolve_latest_run_id(Path("runs"))
        if run_id is None:
            print("No run log found. Use `singular report --id <run_id>`.")
            return 1
        report_format = args.report_output_format or args.output_format
        report(
            run_id=run_id,
            runs_dir=Path("runs"),
            skills_path=Path("mem") / "skills.json",
            output_format=report_format,
            export=args.export,
        )

    elif args.command == "dashboard":
        from .dashboard import run as dashboard_run

        dashboard_run()
    elif args.command == "rollback":
        from .runs.generations import rollback_generation

        _ensure_active_life(resolve_life, args.life)
        try:
            restored = rollback_generation(args.generation)
        except ValueError as exc:
            print(f"Rollback impossible: {exc}", file=sys.stderr)
            return 1
        print(
            "Rollback appliqué: "
            f"generation={restored['generation_id']} "
            f"target={restored['skill_path']}"
        )

    elif args.command == "quickstart":
        if args.name:
            name = args.name
        elif _can_prompt():
            print("🚀 Quickstart Singular")
            name = _prompt_text("Nom de la vie à créer", "New life")
        else:
            name = "New life"
        metadata = bootstrap_life(name, seed=args.seed)
        os.environ["SINGULAR_HOME"] = str(metadata.path)
        print(f"Vie créée: {metadata.name} ({metadata.slug}) → {metadata.path}")
        if _can_prompt() and _prompt_yes_no("Lancer un diagnostic `doctor` maintenant ?"):
            _doctor(fix=False)

    elif args.command == "monitor":
        _ensure_active_life(resolve_life, args.life)
        verbose = args.verbose
        if _can_prompt():
            print("📈 Monitor Singular")
            verbose = _prompt_yes_no("Afficher les détails étendus", default=True)
        from .organisms.status import status

        status(verbose=verbose, output_format=args.output_format)

    elif args.command in {"watch", "veille"}:
        _ensure_active_life(resolve_life, args.life)
        from .watch.daemon import run_watch_daemon

        return run_watch_daemon(
            interval_seconds=args.interval,
            sources=args.sources,
            cpu_budget_percent=args.cpu_budget,
            memory_budget_mb=args.memory_budget,
            dry_run=args.dry_run,
            watch_dir=args.watch_dir,
        )
    elif args.command == "orchestrate":
        _ensure_active_life(resolve_life, args.life)
        if args.orchestrate_command == "run":
            from .orchestrator import run_orchestrator_daemon

            return run_orchestrator_daemon(
                veille_seconds=args.veille_seconds,
                action_seconds=args.action_seconds,
                introspection_seconds=args.introspection_seconds,
                sommeil_seconds=args.sommeil_seconds,
                poll_interval_seconds=args.poll_interval,
                tick_budget_seconds=args.tick_budget,
                lifecycle_config_path=args.lifecycle_config,
                dry_run=args.dry_run,
                safe_mode=args.safe_mode,
            )

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
                items = [
                    {
                        "active": slug == active,
                        "name": meta.name,
                        "slug": slug,
                        "path": str(meta.path),
                        "created_at": meta.created_at,
                    }
                    for slug, meta in sorted(lives.items())
                ]
                if args.output_format == "json":
                    print(json.dumps({"active": active, "lives": items}, ensure_ascii=False))
                elif args.output_format == "table":
                    rows = [
                        [
                            "*" if item["active"] else "",
                            item["name"],
                            item["slug"],
                            item["path"],
                            item["created_at"],
                        ]
                        for item in items
                    ]
                    _print_table(["Active", "Name", "Slug", "Path", "Created"], rows)
                else:
                    for item in items:
                        marker = "*" if item["active"] else " "
                        print(
                            f"{marker} {item['name']} [{item['slug']}] - {item['path']}"
                            f" (créée le {item['created_at']})"
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
        elif args.lives_command == "archive":
            try:
                metadata = archive_life(args.name)
            except KeyError as exc:
                raise SystemExit(f"Vie introuvable: {args.name}") from exc
            print(f"Vie archivée: {metadata.name} ({metadata.slug}) → statut={metadata.status}")
            print("Conseil: exécutez `singular lives memorial <vie> --message \"...\"`.")
        elif args.lives_command == "memorial":
            try:
                memorial_path = memorialize_life(args.name, message=args.message)
            except KeyError as exc:
                raise SystemExit(f"Vie introuvable: {args.name}") from exc
            print(f"Mémorial enregistré: {memorial_path}")
            print("Conseil: exécutez `singular lives clone <vie> --new-name \"...\"`.")
        elif args.lives_command == "clone":
            try:
                metadata = clone_life(args.name, new_name=args.new_name)
            except KeyError as exc:
                raise SystemExit(f"Vie introuvable: {args.name}") from exc
            os.environ["SINGULAR_HOME"] = str(metadata.path)
            print(f"Vie clonée: {metadata.name} ({metadata.slug}) → {metadata.path}")
            print("Conseil: exécutez `singular status --verbose` puis `singular loop --budget-seconds 10`.")
        elif args.lives_command == "relations":
            try:
                payload = list_relations(args.name)
            except KeyError as exc:
                raise SystemExit(f"Vie introuvable: {args.name or 'active'}") from exc
            if args.output_format == "json":
                print(json.dumps(payload, ensure_ascii=False))
            else:
                focus = payload["focus"]
                print(f"Relations pour {focus['name']} ({focus['slug']})")
                print(f"  Parents: {', '.join(focus['parents']) or '-'}")
                print(f"  Enfants: {', '.join(focus['children']) or '-'}")
                print(f"  Alliés: {', '.join(focus['allies']) or '-'}")
                print(f"  Rivaux: {', '.join(focus['rivals']) or '-'}")
                print(f"  Score proximité: {float(focus['proximity_score']):.2f}")
                print(f"Conflits actifs: {len(payload.get('active_conflicts', []))}")
        elif args.lives_command == "ally":
            try:
                meta, other = ally_lives(args.name, args.other)
            except (KeyError, ValueError, PermissionError) as exc:
                raise SystemExit(str(exc)) from exc
            print(f"Alliance enregistrée: {meta.slug} ↔ {other.slug}")
        elif args.lives_command == "rival":
            try:
                meta, other = rival_lives(args.name, args.other)
            except (KeyError, ValueError, PermissionError) as exc:
                raise SystemExit(str(exc)) from exc
            print(f"Rivalité enregistrée: {meta.slug} ⚔ {other.slug}")
        elif args.lives_command == "reconcile":
            try:
                meta, other = reconcile_lives(args.name, args.other)
            except (KeyError, ValueError, PermissionError) as exc:
                raise SystemExit(str(exc)) from exc
            print(f"Réconciliation enregistrée: {meta.slug} ↔ {other.slug}")
        elif args.lives_command == "proximity":
            try:
                meta = set_proximity(args.name, args.score)
            except (KeyError, ValueError, PermissionError) as exc:
                raise SystemExit(str(exc)) from exc
            print(f"Score proximité mis à jour: {meta.slug} = {meta.proximity_score:.2f}")

    elif args.command == "values":
        _ensure_active_life(resolve_life, args.life)
        from .governance.values import load_value_weights

        weights = load_value_weights()
        payload = weights.to_dict()
        if args.values_command != "show":
            raise SystemExit(f"Sous-commande values inconnue: {args.values_command}")
        if args.output_format == "json":
            print(json.dumps({"values": payload}, ensure_ascii=False))
        elif args.output_format == "table":
            rows = [[key, f"{value:.4f}"] for key, value in payload.items()]
            _print_table(["Axe", "Poids"], rows)
        else:
            print("Valeurs critiques:")
            for key, value in payload.items():
                print(f"- {key}: {value:.4f}")

    elif args.command == "policy":
        from dataclasses import replace
        from .governance.policy import (
            PolicySchemaError,
            load_runtime_policy,
            save_runtime_policy,
        )

        try:
            policy = load_runtime_policy()
        except PolicySchemaError as exc:
            print(f"Erreur de validation policy.yaml: {exc}", file=sys.stderr)
            return 1

        if args.policy_command == "show":
            payload = policy.to_payload()
            payload["impact"] = policy.impact_summary()
            if args.output_format == "json":
                print(json.dumps({"policy": payload}, ensure_ascii=False))
            elif args.output_format == "table":
                rows = [[key, str(value)] for key, value in payload.items() if key != "impact"]
                _print_table(["Section", "Valeur"], rows)
                print("Impact:")
                for item in payload["impact"]:
                    print(f"- {item}")
            else:
                print(json.dumps(payload, ensure_ascii=False, indent=2))
                print("Impact:")
                for item in payload["impact"]:
                    print(f"- {item}")
        elif args.policy_command == "set":
            expected_type, field_name = _POLICY_SETTERS[args.key]
            try:
                value = _parse_policy_value(expected_type, args.value)
            except (ValueError, TypeError) as exc:
                print(f"Valeur invalide pour {args.key}: {exc}", file=sys.stderr)
                return 1
            policy = replace(policy, **{field_name: value})
            try:
                save_runtime_policy(policy)
            except PolicySchemaError as exc:
                print(f"Échec validation policy.yaml: {exc}", file=sys.stderr)
                return 1
            print(f"✅ Politique mise à jour: {args.key}={args.value}")
            for item in policy.impact_summary():
                print(f"- {item}")

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

    elif args.command == "beliefs":
        if args.life is not None:
            _ensure_active_life(resolve_life, args.life)
        elif "SINGULAR_HOME" not in os.environ:
            _ensure_active_life(resolve_life, args.life)
        from .beliefs.store import BeliefStore

        store = BeliefStore()
        if args.beliefs_command == "audit":
            beliefs = store.list_beliefs()[: max(0, args.limit)]
            rows = [
                [
                    belief.hypothesis,
                    f"{belief.confidence:.3f}",
                    str(belief.runs),
                    belief.updated_at,
                    belief.evidence,
                ]
                for belief in beliefs
            ]
            if args.output_format == "json":
                print(
                    json.dumps(
                        {"beliefs": [belief.__dict__ for belief in beliefs]},
                        ensure_ascii=False,
                    )
                )
            elif args.output_format == "table":
                if rows:
                    _print_table(
                        ["Hypothesis", "Confidence", "Runs", "Updated", "Evidence"],
                        rows,
                    )
                else:
                    print("Aucune croyance enregistrée.")
            else:
                if not beliefs:
                    print("Aucune croyance enregistrée.")
                for belief in beliefs:
                    print(
                        f"- {belief.hypothesis}: conf={belief.confidence:.3f} "
                        f"runs={belief.runs} updated={belief.updated_at} "
                        f"evidence={belief.evidence}"
                    )
        elif args.beliefs_command == "reset":
            if args.hypothesis:
                deleted = store.reset(hypothesis=args.hypothesis)
                print(f"Croyances supprimées (hypothesis): {deleted}")
            elif args.prefix:
                deleted = store.reset(prefix=args.prefix)
                print(f"Croyances supprimées (prefix): {deleted}")
            else:
                deleted = store.reset()
                print(f"Croyances supprimées (all): {deleted}")

    else:  # pragma: no cover - defensive programming
        raise SystemExit(f"Commande inconnue: {args.command}")

    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
