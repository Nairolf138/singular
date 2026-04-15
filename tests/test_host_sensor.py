from __future__ import annotations

from singular.sensors import host


def test_collect_host_metrics_returns_normalized_payload() -> None:
    metrics = host.collect_host_metrics()

    assert {
        "cpu_percent",
        "cpu_load_1m",
        "ram_used_percent",
        "ram_available_mb",
        "disk_used_percent",
        "disk_free_gb",
        "host_temperature_c",
        "process_cpu_percent",
        "process_rss_mb",
        "host_uptime_s",
        "collection_strategy",
        "metric_status",
    }.issubset(set(metrics))
    assert isinstance(metrics["cpu_percent"], float)
    assert isinstance(metrics["ram_used_percent"], float)
    assert isinstance(metrics["ram_available_mb"], float)
    assert isinstance(metrics["disk_used_percent"], float)
    assert isinstance(metrics["disk_free_gb"], float)
    assert isinstance(metrics["process_cpu_percent"], float)
    assert isinstance(metrics["process_rss_mb"], float)
    assert metrics["host_uptime_s"] is None or isinstance(metrics["host_uptime_s"], float)
    assert isinstance(metrics["metric_status"], dict)
    assert metrics["cpu_load_1m"] is None or isinstance(metrics["cpu_load_1m"], float)
    assert metrics["host_temperature_c"] is None or isinstance(metrics["host_temperature_c"], float)


def test_collect_host_metrics_without_psutil(monkeypatch) -> None:
    monkeypatch.setattr(host, "psutil", None)
    metrics = host.collect_host_metrics()

    assert metrics["host_temperature_c"] is None
    assert metrics["cpu_load_1m"] is None or metrics["cpu_load_1m"] >= 0.0
    assert 0.0 <= metrics["cpu_percent"] <= 100.0
    assert metrics["collection_strategy"] in {"partial_fallback", "minimal_fallback"}
