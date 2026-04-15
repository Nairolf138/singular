"""Unified storage retention configuration and policy reporting.

This module centralizes retention knobs for run artifacts and memory JSONL files.
Configuration is resolved with the following precedence:
1. Environment variables (``SINGULAR_RETENTION_*``)
2. Persisted configuration file (JSON)
3. Built-in defaults
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import os
import shutil
import time
from typing import Any, Mapping

from .io_utils import append_jsonl_line

_DEFAULT_PERSISTED_CONFIG_RELATIVE_PATH = Path("mem") / "retention_policy.json"
_RETENTION_LOG_RELATIVE_PATH = Path("mem") / "retention.log.jsonl"
_BYTES_PER_MB = 1024 * 1024


@dataclass(frozen=True)
class RetentionConfig:
    """Resolved retention limits for all persistent stores."""

    max_runs: int = 20
    max_run_age_days: int = 30
    max_total_runs_size_mb: int = 512
    max_episodic_lines: int = 20_000
    max_episodic_days: int = 90
    max_generations_lines: int = 50_000
    max_generations_days: int = 365


@dataclass(frozen=True)
class PolicyDecision:
    """Decision record for one artifact considered by retention."""

    target: str
    category: str
    action: str
    reason: str
    size_mb: float | None = None
    age_days: float | None = None
    run_id: str | None = None
    active: bool = False


@dataclass(frozen=True)
class PolicyReport:
    """Collection of retention decisions for traceability."""

    generated_at: str
    scope: str
    config: RetentionConfig
    decisions: tuple[PolicyDecision, ...] = field(default_factory=tuple)

    @property
    def summary(self) -> dict[str, int]:
        counts = {"keep": 0, "archive": 0, "delete": 0}
        for decision in self.decisions:
            counts[decision.action] = counts.get(decision.action, 0) + 1
        return counts


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _coerce_positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _walk_total_size(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        try:
            return path.stat().st_size
        except OSError:
            return 0
    total = 0
    for file in path.rglob("*"):
        if not file.is_file():
            continue
        try:
            total += file.stat().st_size
        except OSError:
            continue
    return total


def _latest_mtime(path: Path) -> datetime | None:
    if not path.exists():
        return None
    timestamps: list[float] = []
    try:
        timestamps.append(path.stat().st_mtime)
    except OSError:
        return None
    if path.is_dir():
        for file in path.rglob("*"):
            try:
                timestamps.append(file.stat().st_mtime)
            except OSError:
                continue
    if not timestamps:
        return None
    return datetime.fromtimestamp(max(timestamps), tz=timezone.utc)


def _run_id_from_legacy_file(path: Path) -> str:
    stem = path.stem
    return stem.rsplit("-", 1)[0] if "-" in stem else stem


def _is_active_run(runs_dir: Path, run_id: str) -> bool:
    run_dir = runs_dir / run_id
    if (run_dir / ".active.lock").exists():
        return True
    return any(runs_dir.glob(f"{run_id}-*.jsonl.tmp"))


def _retention_log_path(runs_dir: Path) -> Path:
    base_dir = runs_dir.parent
    return base_dir / _RETENTION_LOG_RELATIVE_PATH


def _safe_delete_path(target: Path) -> tuple[bool, str]:
    if not target.exists():
        return True, "missing"
    tombstone = target.with_name(f".purge-{target.name}-{time.time_ns()}")
    try:
        os.replace(target, tombstone)
    except FileNotFoundError:
        return True, "missing"
    except OSError as exc:
        return False, f"rename_failed:{exc.__class__.__name__}"
    try:
        if tombstone.is_dir():
            shutil.rmtree(tombstone, ignore_errors=False)
        else:
            tombstone.unlink()
    except FileNotFoundError:
        return True, "missing"
    except OSError as exc:
        return False, f"remove_failed:{exc.__class__.__name__}"
    return True, "deleted"


def persisted_retention_config_path(base_dir: Path | None = None) -> Path:
    root = Path(base_dir) if base_dir is not None else Path(os.environ.get("SINGULAR_HOME", "."))
    return root / _DEFAULT_PERSISTED_CONFIG_RELATIVE_PATH


def load_persisted_retention_config(path: Path | None = None) -> Mapping[str, Any]:
    """Load persisted retention config from JSON.

    Expected shape:
    {
      "retention": {"max_runs": 20, ...}
    }
    """

    config_path = path or persisted_retention_config_path()
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, Mapping):
        return {}
    retention = payload.get("retention", payload)
    return retention if isinstance(retention, Mapping) else {}


def load_retention_config(
    *,
    base_dir: Path | None = None,
    environ: Mapping[str, str] | None = None,
    persisted_path: Path | None = None,
) -> RetentionConfig:
    """Resolve retention configuration from env, persisted config, then defaults."""

    env = dict(os.environ if environ is None else environ)
    persisted = load_persisted_retention_config(
        persisted_path or persisted_retention_config_path(base_dir)
    )

    defaults = RetentionConfig()

    def pick(name: str, legacy_env: str | None = None) -> int:
        env_name = f"SINGULAR_RETENTION_{name.upper()}"
        if env_name in env:
            return _coerce_positive_int(env[env_name], getattr(defaults, name))
        if legacy_env and legacy_env in env:
            return _coerce_positive_int(env[legacy_env], getattr(defaults, name))
        if name in persisted:
            return _coerce_positive_int(persisted[name], getattr(defaults, name))
        return getattr(defaults, name)

    return RetentionConfig(
        max_runs=pick("max_runs", legacy_env="SINGULAR_RUNS_KEEP"),
        max_run_age_days=pick("max_run_age_days"),
        max_total_runs_size_mb=pick("max_total_runs_size_mb"),
        max_episodic_lines=pick("max_episodic_lines"),
        max_episodic_days=pick("max_episodic_days"),
        max_generations_lines=pick("max_generations_lines"),
        max_generations_days=pick("max_generations_days"),
    )


def build_runs_policy_report(
    *,
    runs_dir: Path,
    config: RetentionConfig,
    now: datetime | None = None,
) -> PolicyReport:
    """Build retention decisions for run JSONL logs in ``runs_dir``."""

    ref_now = now or _now_utc()
    grouped: dict[str, list[Path]] = {}
    for run_dir in runs_dir.iterdir() if runs_dir.exists() else []:
        if run_dir.is_dir():
            grouped.setdefault(run_dir.name, []).append(run_dir)
    for legacy_file in runs_dir.glob("*.jsonl"):
        grouped.setdefault(_run_id_from_legacy_file(legacy_file), []).append(legacy_file)

    candidates: list[tuple[str, Path, datetime, float, int, bool]] = []
    for run_id, artifacts in grouped.items():
        mtimes = [mtime for artifact in artifacts if (mtime := _latest_mtime(artifact)) is not None]
        if not mtimes:
            continue
        latest_mtime = max(mtimes)
        age_days = (ref_now - latest_mtime).total_seconds() / 86400
        size = sum(_walk_total_size(artifact) for artifact in artifacts)
        primary = runs_dir / run_id if (runs_dir / run_id).exists() else artifacts[0]
        candidates.append((run_id, primary, latest_mtime, age_days, size, _is_active_run(runs_dir, run_id)))

    candidates.sort(key=lambda row: (row[2], row[0]), reverse=True)

    decisions: list[PolicyDecision] = []
    kept_count = 0
    kept_candidates: list[tuple[int, int]] = []
    running_size = 0
    for index, (run_id, target, _mtime, age_days, size, active) in enumerate(candidates):
        size_mb = size / _BYTES_PER_MB
        action = "keep"
        reason = "within_policy"
        if active:
            reason = "active_run_protected"
        elif kept_count >= config.max_runs:
            action = "delete"
            reason = "max_runs"
        elif age_days > config.max_run_age_days:
            action = "delete"
            reason = "max_run_age_days"
        else:
            kept_count += 1
            running_size += size

        decisions.append(
            PolicyDecision(
                target=str(target),
                category="runs",
                action=action,
                reason=reason,
                size_mb=round(size_mb, 4),
                age_days=round(age_days, 4),
                run_id=run_id,
                active=active,
            )
        )
        if action == "keep" and not active:
            kept_candidates.append((index, size))

    if running_size / _BYTES_PER_MB > config.max_total_runs_size_mb:
        for index, size in sorted(kept_candidates, key=lambda row: row[0], reverse=True):
            if running_size / _BYTES_PER_MB <= config.max_total_runs_size_mb:
                break
            decision = decisions[index]
            decisions[index] = PolicyDecision(
                target=decision.target,
                category=decision.category,
                action="delete",
                reason="max_total_runs_size_mb",
                size_mb=decision.size_mb,
                age_days=decision.age_days,
                run_id=decision.run_id,
                active=decision.active,
            )
            running_size -= size

    return PolicyReport(
        generated_at=ref_now.isoformat(),
        scope="runs",
        config=config,
        decisions=tuple(decisions),
    )


def apply_runs_retention(
    *,
    runs_dir: Path,
    config: RetentionConfig,
    now: datetime | None = None,
) -> PolicyReport:
    """Apply retention policy to run JSONL logs and return decision report.

    Files marked as ``delete`` are removed immediately.
    Files marked as ``archive`` are currently kept in place and reported so a
    future archiver can move/compress them deterministically.
    """

    report = build_runs_policy_report(runs_dir=runs_dir, config=config, now=now)
    retention_log = _retention_log_path(runs_dir)
    by_run: dict[str, list[Path]] = {}
    for run_dir in runs_dir.iterdir() if runs_dir.exists() else []:
        if run_dir.is_dir():
            by_run.setdefault(run_dir.name, []).append(run_dir)
    for legacy_file in runs_dir.glob("*.jsonl"):
        by_run.setdefault(_run_id_from_legacy_file(legacy_file), []).append(legacy_file)

    for decision in report.decisions:
        delete_status = "skipped"
        if decision.action == "delete" and not decision.active:
            artifacts = by_run.get(decision.run_id or "", [Path(decision.target)])
            deleted_all = True
            statuses: list[str] = []
            for artifact in artifacts:
                ok, status = _safe_delete_path(artifact)
                statuses.append(f"{artifact.name}:{status}")
                deleted_all = deleted_all and ok
            delete_status = "deleted" if deleted_all else "error"
            if statuses:
                delete_status = f"{delete_status}:{','.join(statuses)}"

        append_jsonl_line(
            retention_log,
            {
                "ts": _now_utc().isoformat(),
                "scope": "runs",
                "run_id": decision.run_id,
                "target": decision.target,
                "action": decision.action,
                "reason": decision.reason,
                "active": decision.active,
                "size_mb": decision.size_mb,
                "age_days": decision.age_days,
                "delete_status": delete_status,
            },
            with_lock=True,
        )
    return report
