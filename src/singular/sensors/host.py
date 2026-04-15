"""Host metrics collector with psutil-first strategy.

This module exposes a single public API:

``collect_host_metrics()``

The function always returns the same normalized payload and never raises due
system-metric collection failures.
"""

from __future__ import annotations

import os
import platform
import shutil
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:  # pragma: no cover - import branch depends on optional dependency
    import psutil  # type: ignore[import-untyped]
except Exception:  # pragma: no cover - optional dependency
    psutil = None

_MB = 1024 * 1024
_GB = 1024 * 1024 * 1024
_LAST_PROCESS_SAMPLE: "_ProcessSample | None" = None
_STATUS_AVAILABLE = "available"
_STATUS_PARTIAL = "partial"
_STATUS_UNSUPPORTED = "unsupported"


@dataclass
class _ProcessSample:
    wall_time: float
    cpu_time: float


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _metric_payload(
    *,
    value: float | None,
    unit: str,
    status: str,
    reason: str | None = None,
    last_seen_at: str | None = None,
) -> dict[str, Any]:
    return {
        "value": value,
        "unit": unit,
        "status": status,
        "reason": reason,
        "last_seen_at": last_seen_at,
    }


def _collect_memory_stdlib() -> tuple[float, float]:
    total_bytes = 0.0
    avail_bytes = 0.0

    if hasattr(os, "sysconf"):
        try:
            page_size = float(os.sysconf("SC_PAGE_SIZE"))
            phys_pages = float(os.sysconf("SC_PHYS_PAGES"))
            total_bytes = page_size * phys_pages
        except (ValueError, OSError, TypeError):
            total_bytes = 0.0

        try:
            avail_pages = float(os.sysconf("SC_AVPHYS_PAGES"))
            avail_bytes = page_size * avail_pages
        except (ValueError, OSError, TypeError, UnboundLocalError):
            avail_bytes = 0.0

    if total_bytes <= 0.0:
        return 0.0, 0.0

    used_bytes = max(0.0, total_bytes - max(avail_bytes, 0.0))
    used_percent = (used_bytes / total_bytes) * 100.0
    return max(0.0, min(used_percent, 100.0)), max(avail_bytes / _MB, 0.0)


def _collect_disk_stdlib() -> tuple[float, float]:
    path = Path.cwd()
    try:
        usage = shutil.disk_usage(path)
    except OSError:
        return 0.0, 0.0

    total = float(usage.total)
    free = float(usage.free)
    if total <= 0.0:
        return 0.0, max(free / _GB, 0.0)

    used_percent = ((total - free) / total) * 100.0
    return max(0.0, min(used_percent, 100.0)), max(free / _GB, 0.0)


def _collect_process_stdlib() -> tuple[float, float]:
    global _LAST_PROCESS_SAMPLE

    rss_mb = 0.0
    try:
        import resource

        rss_raw = _safe_float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        if os.name == "posix" and os.uname().sysname == "Darwin":
            rss_mb = max(rss_raw / _MB, 0.0)
        else:
            rss_mb = max((rss_raw * 1024.0) / _MB, 0.0)
    except Exception:
        rss_mb = 0.0

    cpu_percent = 0.0
    try:
        current = _ProcessSample(wall_time=time.monotonic(), cpu_time=time.process_time())
        previous = _LAST_PROCESS_SAMPLE
        _LAST_PROCESS_SAMPLE = current
        if previous is not None:
            wall_delta = current.wall_time - previous.wall_time
            cpu_delta = current.cpu_time - previous.cpu_time
            if wall_delta > 0.0:
                cpu_percent = max(0.0, min((cpu_delta / wall_delta) * 100.0, 100.0))
    except Exception:
        cpu_percent = 0.0

    return cpu_percent, rss_mb


def _collect_temperatures_psutil() -> float | None:
    if psutil is None:
        return None
    try:
        sensors = psutil.sensors_temperatures()  # type: ignore[attr-defined]
    except Exception:
        return None
    if not sensors:
        return None

    values: list[float] = []
    for entries in sensors.values():
        for entry in entries:
            current = _safe_float(getattr(entry, "current", None), default=-1.0)
            if current >= 0.0:
                values.append(current)

    if not values:
        return None
    return sum(values) / len(values)


def _collect_uptime_seconds() -> tuple[float | None, str | None]:
    if psutil is not None:
        try:
            boot_time = _safe_float(psutil.boot_time())  # type: ignore[attr-defined]
            now = time.time()
            return max(now - boot_time, 0.0), None
        except Exception:
            pass
    if platform.system() == "Linux":
        try:
            raw = Path("/proc/uptime").read_text(encoding="utf-8").split()[0]
            return max(_safe_float(raw), 0.0), None
        except Exception:
            return None, "linux_uptime_unavailable"
    return None, "uptime_probe_not_supported_on_platform"


def collect_host_metrics() -> dict[str, Any]:
    """Return normalized host metrics.

    Keys are stable and always present.
    """

    collected_at = _utc_now_iso()
    cpu_percent = 0.0
    cpu_load_1m: float | None = None
    ram_used_percent = 0.0
    ram_available_mb = 0.0
    disk_used_percent = 0.0
    disk_free_gb = 0.0
    host_temperature_c: float | None = None
    process_cpu_percent = 0.0
    process_rss_mb = 0.0
    host_uptime_s: float | None = None
    strategy = "minimal_fallback"

    metric_statuses: dict[str, dict[str, Any]] = {
        "cpu_percent": _metric_payload(value=None, unit="percent", status=_STATUS_UNSUPPORTED, reason="cpu_probe_unavailable"),
        "cpu_load_1m": _metric_payload(value=None, unit="load", status=_STATUS_UNSUPPORTED, reason="load_probe_unavailable"),
        "ram_used_percent": _metric_payload(value=None, unit="percent", status=_STATUS_UNSUPPORTED, reason="memory_probe_unavailable"),
        "ram_available_mb": _metric_payload(value=None, unit="MB", status=_STATUS_UNSUPPORTED, reason="memory_probe_unavailable"),
        "disk_used_percent": _metric_payload(value=None, unit="percent", status=_STATUS_UNSUPPORTED, reason="disk_probe_unavailable"),
        "disk_free_gb": _metric_payload(value=None, unit="GB", status=_STATUS_UNSUPPORTED, reason="disk_probe_unavailable"),
        "host_temperature_c": _metric_payload(
            value=None,
            unit="C",
            status=_STATUS_UNSUPPORTED,
            reason="temperature_sensor_unavailable",
        ),
        "process_cpu_percent": _metric_payload(
            value=None,
            unit="percent",
            status=_STATUS_UNSUPPORTED,
            reason="process_probe_unavailable",
        ),
        "process_rss_mb": _metric_payload(value=None, unit="MB", status=_STATUS_UNSUPPORTED, reason="process_probe_unavailable"),
        "host_uptime_s": _metric_payload(value=None, unit="s", status=_STATUS_UNSUPPORTED, reason="uptime_probe_unavailable"),
    }

    if psutil is not None:
        strategy = "primary"
        try:
            cpu_percent = max(0.0, min(_safe_float(psutil.cpu_percent(interval=None)), 100.0))
            metric_statuses["cpu_percent"] = _metric_payload(
                value=cpu_percent, unit="percent", status=_STATUS_AVAILABLE, last_seen_at=collected_at
            )
        except Exception:
            cpu_percent = 0.0

        try:
            load = os.getloadavg()[0]
            cpu_load_1m = max(_safe_float(load), 0.0)
            metric_statuses["cpu_load_1m"] = _metric_payload(
                value=cpu_load_1m, unit="load", status=_STATUS_AVAILABLE, last_seen_at=collected_at
            )
        except Exception:
            cpu_load_1m = None
            metric_statuses["cpu_load_1m"] = _metric_payload(
                value=None,
                unit="load",
                status=_STATUS_PARTIAL,
                reason="loadavg_not_supported_on_platform",
            )

        try:
            vm = psutil.virtual_memory()
            ram_used_percent = max(0.0, min(_safe_float(getattr(vm, "percent", 0.0)), 100.0))
            ram_available_mb = max(_safe_float(getattr(vm, "available", 0.0)) / _MB, 0.0)
            metric_statuses["ram_used_percent"] = _metric_payload(
                value=ram_used_percent, unit="percent", status=_STATUS_AVAILABLE, last_seen_at=collected_at
            )
            metric_statuses["ram_available_mb"] = _metric_payload(
                value=ram_available_mb, unit="MB", status=_STATUS_AVAILABLE, last_seen_at=collected_at
            )
        except Exception:
            ram_used_percent, ram_available_mb = _collect_memory_stdlib()
            metric_statuses["ram_used_percent"] = _metric_payload(
                value=ram_used_percent, unit="percent", status=_STATUS_PARTIAL, reason="psutil_virtual_memory_failed"
            )
            metric_statuses["ram_available_mb"] = _metric_payload(
                value=ram_available_mb, unit="MB", status=_STATUS_PARTIAL, reason="psutil_virtual_memory_failed"
            )

        try:
            du = psutil.disk_usage(str(Path.cwd()))
            disk_used_percent = max(0.0, min(_safe_float(getattr(du, "percent", 0.0)), 100.0))
            disk_free_gb = max(_safe_float(getattr(du, "free", 0.0)) / _GB, 0.0)
            metric_statuses["disk_used_percent"] = _metric_payload(
                value=disk_used_percent, unit="percent", status=_STATUS_AVAILABLE, last_seen_at=collected_at
            )
            metric_statuses["disk_free_gb"] = _metric_payload(
                value=disk_free_gb, unit="GB", status=_STATUS_AVAILABLE, last_seen_at=collected_at
            )
        except Exception:
            disk_used_percent, disk_free_gb = _collect_disk_stdlib()
            metric_statuses["disk_used_percent"] = _metric_payload(
                value=disk_used_percent, unit="percent", status=_STATUS_PARTIAL, reason="psutil_disk_usage_failed"
            )
            metric_statuses["disk_free_gb"] = _metric_payload(
                value=disk_free_gb, unit="GB", status=_STATUS_PARTIAL, reason="psutil_disk_usage_failed"
            )

        host_temperature_c = _collect_temperatures_psutil()
        if host_temperature_c is not None:
            metric_statuses["host_temperature_c"] = _metric_payload(
                value=host_temperature_c, unit="C", status=_STATUS_AVAILABLE, last_seen_at=collected_at
            )
        else:
            metric_statuses["host_temperature_c"] = _metric_payload(
                value=None,
                unit="C",
                status=_STATUS_PARTIAL,
                reason="temperature_sensor_not_exposed_by_os",
            )

        try:
            process = psutil.Process(os.getpid())
            process_cpu_percent = max(0.0, min(_safe_float(process.cpu_percent(interval=None)), 100.0))
            process_rss_mb = max(_safe_float(process.memory_info().rss) / _MB, 0.0)
            metric_statuses["process_cpu_percent"] = _metric_payload(
                value=process_cpu_percent, unit="percent", status=_STATUS_AVAILABLE, last_seen_at=collected_at
            )
            metric_statuses["process_rss_mb"] = _metric_payload(
                value=process_rss_mb, unit="MB", status=_STATUS_AVAILABLE, last_seen_at=collected_at
            )
        except Exception:
            process_cpu_percent, process_rss_mb = _collect_process_stdlib()
            metric_statuses["process_cpu_percent"] = _metric_payload(
                value=process_cpu_percent, unit="percent", status=_STATUS_PARTIAL, reason="psutil_process_probe_failed"
            )
            metric_statuses["process_rss_mb"] = _metric_payload(
                value=process_rss_mb, unit="MB", status=_STATUS_PARTIAL, reason="psutil_process_probe_failed"
            )
    else:
        strategy = "partial_fallback"
        try:
            cpu_percent = max(0.0, min(_safe_float(os.getloadavg()[0]), 100.0))
            metric_statuses["cpu_percent"] = _metric_payload(
                value=cpu_percent,
                unit="percent",
                status=_STATUS_PARTIAL,
                reason="loadavg_used_as_cpu_proxy",
                last_seen_at=collected_at,
            )
        except Exception:
            cpu_percent = 0.0
            metric_statuses["cpu_percent"] = _metric_payload(
                value=None,
                unit="percent",
                status=_STATUS_UNSUPPORTED,
                reason="cpu_probe_unavailable_without_psutil",
            )

        try:
            cpu_load_1m = max(_safe_float(os.getloadavg()[0]), 0.0)
            metric_statuses["cpu_load_1m"] = _metric_payload(
                value=cpu_load_1m, unit="load", status=_STATUS_PARTIAL, reason="loadavg_stdlib_fallback", last_seen_at=collected_at
            )
        except Exception:
            cpu_load_1m = None
            metric_statuses["cpu_load_1m"] = _metric_payload(
                value=None, unit="load", status=_STATUS_UNSUPPORTED, reason="loadavg_not_supported_on_platform"
            )

        ram_used_percent, ram_available_mb = _collect_memory_stdlib()
        if ram_available_mb > 0.0:
            metric_statuses["ram_used_percent"] = _metric_payload(
                value=ram_used_percent, unit="percent", status=_STATUS_PARTIAL, reason="memory_stdlib_fallback", last_seen_at=collected_at
            )
            metric_statuses["ram_available_mb"] = _metric_payload(
                value=ram_available_mb, unit="MB", status=_STATUS_PARTIAL, reason="memory_stdlib_fallback", last_seen_at=collected_at
            )
        disk_used_percent, disk_free_gb = _collect_disk_stdlib()
        if disk_free_gb > 0.0 or disk_used_percent > 0.0:
            metric_statuses["disk_used_percent"] = _metric_payload(
                value=disk_used_percent, unit="percent", status=_STATUS_PARTIAL, reason="disk_stdlib_fallback", last_seen_at=collected_at
            )
            metric_statuses["disk_free_gb"] = _metric_payload(
                value=disk_free_gb, unit="GB", status=_STATUS_PARTIAL, reason="disk_stdlib_fallback", last_seen_at=collected_at
            )
        process_cpu_percent, process_rss_mb = _collect_process_stdlib()
        metric_statuses["process_cpu_percent"] = _metric_payload(
            value=process_cpu_percent, unit="percent", status=_STATUS_PARTIAL, reason="process_stdlib_fallback", last_seen_at=collected_at
        )
        metric_statuses["process_rss_mb"] = _metric_payload(
            value=process_rss_mb, unit="MB", status=_STATUS_PARTIAL, reason="process_stdlib_fallback", last_seen_at=collected_at
        )

    host_uptime_s, uptime_reason = _collect_uptime_seconds()
    if host_uptime_s is not None:
        metric_statuses["host_uptime_s"] = _metric_payload(
            value=host_uptime_s, unit="s", status=_STATUS_AVAILABLE, last_seen_at=collected_at
        )
    else:
        metric_statuses["host_uptime_s"] = _metric_payload(
            value=None, unit="s", status=_STATUS_UNSUPPORTED, reason=uptime_reason or "uptime_probe_unavailable"
        )

    if strategy != "primary":
        has_minimal_signal = any(metric_statuses[name]["value"] is not None for name in ("host_uptime_s", "cpu_load_1m", "ram_available_mb"))
        cpu_or_disk_unavailable = (
            metric_statuses["cpu_percent"]["status"] == _STATUS_UNSUPPORTED
            and metric_statuses["disk_used_percent"]["status"] == _STATUS_UNSUPPORTED
        )
        if has_minimal_signal and cpu_or_disk_unavailable:
            strategy = "minimal_fallback"

    payload: dict[str, Any] = {
        "cpu_percent": cpu_percent,
        "cpu_load_1m": cpu_load_1m,
        "ram_used_percent": ram_used_percent,
        "ram_available_mb": ram_available_mb,
        "disk_used_percent": disk_used_percent,
        "disk_free_gb": disk_free_gb,
        "host_temperature_c": host_temperature_c,
        "process_cpu_percent": process_cpu_percent,
        "process_rss_mb": process_rss_mb,
        "host_uptime_s": host_uptime_s,
        "collection_strategy": strategy,
        "metric_status": metric_statuses,
    }
    return payload
