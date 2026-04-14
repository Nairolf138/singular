"""Host metrics collector with psutil-first strategy.

This module exposes a single public API:

``collect_host_metrics()``

The function always returns the same normalized payload and never raises due
system-metric collection failures.
"""

from __future__ import annotations

import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:  # pragma: no cover - import branch depends on optional dependency
    import psutil  # type: ignore[import-untyped]
except Exception:  # pragma: no cover - optional dependency
    psutil = None

_MB = 1024 * 1024
_GB = 1024 * 1024 * 1024
_LAST_PROCESS_SAMPLE: "_ProcessSample | None" = None


@dataclass
class _ProcessSample:
    wall_time: float
    cpu_time: float


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


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


def collect_host_metrics() -> dict[str, float | None]:
    """Return normalized host metrics.

    Keys are stable and always present.
    """

    cpu_percent = 0.0
    cpu_load_1m: float | None = None
    ram_used_percent = 0.0
    ram_available_mb = 0.0
    disk_used_percent = 0.0
    disk_free_gb = 0.0
    host_temperature_c: float | None = None
    process_cpu_percent = 0.0
    process_rss_mb = 0.0

    if psutil is not None:
        try:
            cpu_percent = max(0.0, min(_safe_float(psutil.cpu_percent(interval=None)), 100.0))
        except Exception:
            cpu_percent = 0.0

        try:
            load = os.getloadavg()[0]
            cpu_load_1m = max(_safe_float(load), 0.0)
        except Exception:
            cpu_load_1m = None

        try:
            vm = psutil.virtual_memory()
            ram_used_percent = max(0.0, min(_safe_float(getattr(vm, "percent", 0.0)), 100.0))
            ram_available_mb = max(_safe_float(getattr(vm, "available", 0.0)) / _MB, 0.0)
        except Exception:
            ram_used_percent, ram_available_mb = _collect_memory_stdlib()

        try:
            du = psutil.disk_usage(str(Path.cwd()))
            disk_used_percent = max(0.0, min(_safe_float(getattr(du, "percent", 0.0)), 100.0))
            disk_free_gb = max(_safe_float(getattr(du, "free", 0.0)) / _GB, 0.0)
        except Exception:
            disk_used_percent, disk_free_gb = _collect_disk_stdlib()

        host_temperature_c = _collect_temperatures_psutil()

        try:
            process = psutil.Process(os.getpid())
            process_cpu_percent = max(0.0, min(_safe_float(process.cpu_percent(interval=None)), 100.0))
            process_rss_mb = max(_safe_float(process.memory_info().rss) / _MB, 0.0)
        except Exception:
            process_cpu_percent, process_rss_mb = _collect_process_stdlib()
    else:
        try:
            cpu_percent = max(0.0, min(_safe_float(os.getloadavg()[0]), 100.0))
        except Exception:
            cpu_percent = 0.0

        try:
            cpu_load_1m = max(_safe_float(os.getloadavg()[0]), 0.0)
        except Exception:
            cpu_load_1m = None

        ram_used_percent, ram_available_mb = _collect_memory_stdlib()
        disk_used_percent, disk_free_gb = _collect_disk_stdlib()
        process_cpu_percent, process_rss_mb = _collect_process_stdlib()

    payload: dict[str, float | None] = {
        "cpu_percent": cpu_percent,
        "cpu_load_1m": cpu_load_1m,
        "ram_used_percent": ram_used_percent,
        "ram_available_mb": ram_available_mb,
        "disk_used_percent": disk_used_percent,
        "disk_free_gb": disk_free_gb,
        "host_temperature_c": host_temperature_c,
        "process_cpu_percent": process_cpu_percent,
        "process_rss_mb": process_rss_mb,
    }
    return payload
