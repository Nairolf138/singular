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
from typing import Any, Mapping

_DEFAULT_PERSISTED_CONFIG_RELATIVE_PATH = Path("mem") / "retention_policy.json"
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
    candidates = []
    for file in runs_dir.glob("*.jsonl"):
        try:
            stat = file.stat()
        except OSError:
            continue
        mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
        age_days = (ref_now - mtime).total_seconds() / 86400
        size = stat.st_size
        candidates.append((file, mtime, age_days, size))

    candidates.sort(key=lambda row: (row[1], row[0].name), reverse=True)

    decisions: list[PolicyDecision] = []
    running_size = 0
    for index, (file, _mtime, age_days, size) in enumerate(candidates):
        size_mb = size / _BYTES_PER_MB
        action = "keep"
        reason = "within_policy"
        if index >= config.max_runs:
            action = "delete"
            reason = "max_runs"
        elif age_days > config.max_run_age_days:
            action = "archive"
            reason = "max_run_age_days"
        elif (running_size + size) / _BYTES_PER_MB > config.max_total_runs_size_mb:
            action = "archive"
            reason = "max_total_runs_size_mb"

        if action == "keep":
            running_size += size

        decisions.append(
            PolicyDecision(
                target=str(file),
                category="runs",
                action=action,
                reason=reason,
                size_mb=round(size_mb, 4),
                age_days=round(age_days, 4),
            )
        )

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
    for decision in report.decisions:
        if decision.action != "delete":
            continue
        try:
            Path(decision.target).unlink()
        except FileNotFoundError:
            continue
    return report
