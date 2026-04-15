"""Persistent host-metrics storage and simple aggregations."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
import os

from singular.memory import append_jsonl_line_safe, get_mem_dir

_DEFAULT_RETENTION_SAMPLES = 2000
_DEFAULT_WINDOWS = (5, 20, 60)
_METRICS_KEYS = (
    "cpu_percent",
    "ram_used_percent",
    "disk_used_percent",
    "host_temperature_c",
    "process_cpu_percent",
    "process_rss_mb",
    "cpu_load_1m",
    "ram_available_mb",
    "disk_free_gb",
    "host_uptime_s",
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def host_metrics_file() -> Path:
    """Return the host metrics JSONL storage path."""
    return get_mem_dir() / "host_metrics.jsonl"


def _retention_samples() -> int:
    raw = os.getenv("SINGULAR_HOST_METRICS_RETENTION_SAMPLES", str(_DEFAULT_RETENTION_SAMPLES))
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_RETENTION_SAMPLES
    return max(1, value)


def _aggregation_windows() -> tuple[int, ...]:
    raw = os.getenv("SINGULAR_HOST_METRICS_WINDOWS", "")
    if not raw.strip():
        return _DEFAULT_WINDOWS
    windows: list[int] = []
    for token in raw.split(","):
        try:
            candidate = int(token.strip())
        except ValueError:
            continue
        if candidate > 0:
            windows.append(candidate)
    return tuple(sorted(set(windows))) or _DEFAULT_WINDOWS


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_metric_value(metrics: dict[str, Any], key: str) -> float | None:
    raw = metrics.get(key)
    if isinstance(raw, dict):
        return _safe_float(raw.get("value"))
    return _safe_float(raw)


def _extract_metric_snapshot(metrics: dict[str, Any], key: str) -> dict[str, Any] | None:
    candidate = metrics.get(key)
    if not isinstance(candidate, dict):
        return None
    value = _safe_float(candidate.get("value"))
    return {
        "value": value,
        "unit": candidate.get("unit"),
        "status": candidate.get("status"),
        "reason": candidate.get("reason"),
        "last_seen_at": candidate.get("last_seen_at"),
    }


def _coerce_metric_status_block(metrics: dict[str, Any]) -> dict[str, Any]:
    explicit = metrics.get("metric_status")
    if isinstance(explicit, dict):
        return explicit
    snapshots: dict[str, Any] = {}
    for key in _METRICS_KEYS:
        snapshot = _extract_metric_snapshot(metrics, key)
        if snapshot is not None:
            snapshots[key] = snapshot
    return snapshots


def append_host_metrics_sample(metrics: dict[str, Any]) -> None:
    """Append one host sample and enforce retention."""

    path = host_metrics_file()
    payload = {
        "ts": _utc_now_iso(),
        "metrics": {key: _extract_metric_value(metrics, key) for key in _METRICS_KEYS},
        "metric_status": _coerce_metric_status_block(metrics),
        "collection_strategy": metrics.get("collection_strategy"),
    }
    append_jsonl_line_safe(path, payload)
    _trim_retention(path=path, retention=_retention_samples())


def _trim_retention(*, path: Path, retention: int) -> None:
    if retention <= 0 or not path.exists():
        return
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    if len(lines) <= retention:
        return
    path.write_text("\n".join(lines[-retention:]) + "\n", encoding="utf-8")


def load_host_metrics_samples(*, limit: int | None = None) -> list[dict[str, Any]]:
    """Load persisted host metrics samples."""

    path = host_metrics_file()
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    if limit is not None and limit > 0:
        lines = lines[-limit:]
    samples: list[dict[str, Any]] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            samples.append(payload)
    return samples


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _variance(values: list[float], mean: float) -> float:
    if len(values) <= 1:
        return 0.0
    return sum((value - mean) ** 2 for value in values) / len(values)


def compute_host_metrics_aggregates(
    samples: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Compute rolling averages, peaks and variances on persisted samples."""

    if samples is None:
        samples = load_host_metrics_samples(limit=max(_aggregation_windows()) * 4)
    windows = _aggregation_windows()
    metrics_by_key: dict[str, list[float]] = {key: [] for key in _METRICS_KEYS}
    for sample in samples:
        metrics = sample.get("metrics")
        if not isinstance(metrics, dict):
            continue
        for key in _METRICS_KEYS:
            value = _extract_metric_value(metrics, key)
            if value is not None:
                metrics_by_key[key].append(value)

    rolling_means: dict[str, dict[str, float]] = {}
    peaks: dict[str, float] = {}
    variances: dict[str, float] = {}
    for key, values in metrics_by_key.items():
        if not values:
            continue
        peaks[key] = max(values)
        mean_all = _mean(values)
        variances[key] = _variance(values, mean_all)
        rolling_means[key] = {
            str(window): _mean(values[-window:]) for window in windows if len(values) >= 1
        }

    return {
        "sample_count": len(samples),
        "windows": list(windows),
        "rolling_means": rolling_means,
        "peaks": peaks,
        "variance": variances,
        "latest": samples[-1] if samples else None,
    }


def summarize_environmental_impact(aggregates: dict[str, Any] | None) -> dict[str, Any]:
    """Summarize host environmental pressure and expected decision impact."""

    if not isinstance(aggregates, dict):
        return {
            "pressure_score": 0.0,
            "variance_score": 0.0,
            "impact_level": "low",
            "decision_bias": "balanced",
        }
    rolling = aggregates.get("rolling_means", {})
    variance = aggregates.get("variance", {})
    cpu_20 = _safe_float(((rolling.get("cpu_percent") or {}).get("20"))) if isinstance(rolling, dict) else None
    ram_20 = _safe_float(((rolling.get("ram_used_percent") or {}).get("20"))) if isinstance(rolling, dict) else None
    temp_20 = _safe_float(((rolling.get("host_temperature_c") or {}).get("20"))) if isinstance(rolling, dict) else None
    cpu_pressure = max(0.0, min((cpu_20 or 0.0) / 100.0, 1.0))
    ram_pressure = max(0.0, min((ram_20 or 0.0) / 100.0, 1.0))
    thermal_pressure = max(0.0, min((temp_20 or 0.0) / 95.0, 1.0))
    pressure_score = (cpu_pressure * 0.45) + (ram_pressure * 0.35) + (thermal_pressure * 0.2)

    cpu_var = _safe_float((variance or {}).get("cpu_percent")) if isinstance(variance, dict) else None
    ram_var = _safe_float((variance or {}).get("ram_used_percent")) if isinstance(variance, dict) else None
    variance_score = max(0.0, min((((cpu_var or 0.0) / 400.0) + ((ram_var or 0.0) / 400.0)) / 2.0, 1.0))

    if pressure_score >= 0.8:
        level = "critical"
    elif pressure_score >= 0.6:
        level = "high"
    elif pressure_score >= 0.4:
        level = "moderate"
    else:
        level = "low"

    if pressure_score >= 0.65 or variance_score >= 0.55:
        bias = "robustesse"
    elif pressure_score <= 0.25 and variance_score <= 0.2:
        bias = "efficacite_exploration"
    else:
        bias = "balanced"

    return {
        "pressure_score": round(pressure_score, 4),
        "variance_score": round(variance_score, 4),
        "impact_level": level,
        "decision_bias": bias,
    }
