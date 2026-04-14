from __future__ import annotations

import types

from singular.sensors import host


class _FakeProcess:
    def __init__(self, cpu_percent: float, rss_bytes: int) -> None:
        self._cpu_percent = cpu_percent
        self._rss_bytes = rss_bytes

    def cpu_percent(self, interval=None):
        return self._cpu_percent

    def memory_info(self):
        return types.SimpleNamespace(rss=self._rss_bytes)


class _FakePsutil:
    def __init__(
        self,
        *,
        cpu_percent: float,
        ram_percent: float,
        ram_available_bytes: int,
        disk_percent: float,
        disk_free_bytes: int,
        process_cpu_percent: float,
        process_rss_bytes: int,
        temperatures: dict[str, list[object]] | None,
    ) -> None:
        self._cpu_percent = cpu_percent
        self._vm = types.SimpleNamespace(percent=ram_percent, available=ram_available_bytes)
        self._du = types.SimpleNamespace(percent=disk_percent, free=disk_free_bytes)
        self._process = _FakeProcess(process_cpu_percent, process_rss_bytes)
        self._temperatures = temperatures

    def cpu_percent(self, interval=None):
        return self._cpu_percent

    def virtual_memory(self):
        return self._vm

    def disk_usage(self, _path: str):
        return self._du

    def sensors_temperatures(self):
        return self._temperatures

    def Process(self, _pid: int):
        return self._process


def test_collect_host_metrics_nominal_with_psutil(monkeypatch) -> None:
    fake_psutil = _FakePsutil(
        cpu_percent=37.5,
        ram_percent=62.0,
        ram_available_bytes=3 * 1024 * 1024 * 1024,
        disk_percent=41.0,
        disk_free_bytes=500 * 1024 * 1024 * 1024,
        process_cpu_percent=12.0,
        process_rss_bytes=256 * 1024 * 1024,
        temperatures={
            "coretemp": [
                types.SimpleNamespace(current=60.0),
                types.SimpleNamespace(current=70.0),
            ]
        },
    )
    monkeypatch.setattr(host, "psutil", fake_psutil)
    monkeypatch.setattr(host.os, "getloadavg", lambda: (1.25, 0.9, 0.7))

    metrics = host.collect_host_metrics()

    assert metrics["cpu_percent"] == 37.5
    assert metrics["cpu_load_1m"] == 1.25
    assert metrics["ram_used_percent"] == 62.0
    assert metrics["ram_available_mb"] == 3072.0
    assert metrics["disk_used_percent"] == 41.0
    assert metrics["disk_free_gb"] == 500.0
    assert metrics["host_temperature_c"] == 65.0
    assert metrics["process_cpu_percent"] == 12.0
    assert metrics["process_rss_mb"] == 256.0


def test_collect_host_metrics_handles_unavailable_sensors(monkeypatch) -> None:
    monkeypatch.setattr(host, "psutil", None)
    monkeypatch.setattr(host.os, "getloadavg", lambda: (_ for _ in ()).throw(OSError("unsupported")))
    monkeypatch.setattr(host.os, "sysconf", lambda _key: (_ for _ in ()).throw(OSError("unsupported")))
    monkeypatch.setattr(host.shutil, "disk_usage", lambda _path: (_ for _ in ()).throw(OSError("unsupported")))
    monkeypatch.setattr(host, "_collect_process_stdlib", lambda: (0.0, 0.0))

    metrics = host.collect_host_metrics()

    assert metrics["cpu_percent"] == 0.0
    assert metrics["cpu_load_1m"] is None
    assert metrics["ram_used_percent"] == 0.0
    assert metrics["ram_available_mb"] == 0.0
    assert metrics["disk_used_percent"] == 0.0
    assert metrics["disk_free_gb"] == 0.0
    assert metrics["host_temperature_c"] is None
    assert metrics["process_cpu_percent"] == 0.0
    assert metrics["process_rss_mb"] == 0.0


def test_collect_host_metrics_clamps_outlier_values(monkeypatch) -> None:
    fake_psutil = _FakePsutil(
        cpu_percent=999.0,
        ram_percent=-25.0,
        ram_available_bytes=-1,
        disk_percent=150.0,
        disk_free_bytes=-500,
        process_cpu_percent=999.0,
        process_rss_bytes=-1,
        temperatures={
            "thermal": [
                types.SimpleNamespace(current=-10.0),
                types.SimpleNamespace(current="not-a-number"),
            ]
        },
    )
    monkeypatch.setattr(host, "psutil", fake_psutil)
    monkeypatch.setattr(host.os, "getloadavg", lambda: (-4.0, 0.0, 0.0))

    metrics = host.collect_host_metrics()

    assert metrics["cpu_percent"] == 100.0
    assert metrics["cpu_load_1m"] == 0.0
    assert metrics["ram_used_percent"] == 0.0
    assert metrics["ram_available_mb"] == 0.0
    assert metrics["disk_used_percent"] == 100.0
    assert metrics["disk_free_gb"] == 0.0
    assert metrics["host_temperature_c"] is None
    assert metrics["process_cpu_percent"] == 100.0
    assert metrics["process_rss_mb"] == 0.0


def test_collect_host_metrics_unit_conversions(monkeypatch) -> None:
    one_mb = 1024 * 1024
    one_gb = 1024 * 1024 * 1024

    fake_psutil = _FakePsutil(
        cpu_percent=10.0,
        ram_percent=10.0,
        ram_available_bytes=1536 * one_mb,
        disk_percent=20.0,
        disk_free_bytes=250 * one_gb,
        process_cpu_percent=5.0,
        process_rss_bytes=512 * one_mb,
        temperatures={"chip": [types.SimpleNamespace(current=45.0)]},
    )

    monkeypatch.setattr(host, "psutil", fake_psutil)
    monkeypatch.setattr(host.os, "getloadavg", lambda: (0.5, 0.2, 0.1))

    metrics = host.collect_host_metrics()

    assert metrics["ram_available_mb"] == 1536.0
    assert metrics["disk_free_gb"] == 250.0
    assert metrics["process_rss_mb"] == 512.0
