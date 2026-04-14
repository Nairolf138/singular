import sys
import time
import types

from singular.events import EventBus
from singular.perception import capture_signals, reset_perception_state
from singular.memory import add_episode, read_episodes


def test_capture_and_persist_signals(tmp_path, monkeypatch):
    reset_perception_state()
    # Prepare optional file sensor
    sensor_file = tmp_path / "sensor.txt"
    sensor_file.write_text("42", encoding="utf-8")
    monkeypatch.setenv("SINGULAR_SENSOR_FILE", str(sensor_file))

    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    (sandbox / "app.py").write_text("# TODO: cleanup\n", encoding="utf-8")
    (sandbox / "run.log").write_text("boot\n", encoding="utf-8")

    # Capture signals
    signals = capture_signals(sandbox_root=sandbox)
    assert "temperature" in signals
    assert "is_daytime" in signals
    assert "noise" in signals
    assert signals.get("file") == "42"
    assert "artifact_events" in signals

    # Persist and verify
    episodic = tmp_path / "mem" / "episodic.jsonl"
    add_episode({"event": "perception", **signals}, path=episodic)
    episodes = read_episodes(path=episodic)
    assert episodes[0]["event"] == "perception"
    for key in ["temperature", "is_daytime", "noise", "file", "artifact_events"]:
        assert key in episodes[0]


def test_weather_api_timeout(monkeypatch):
    reset_perception_state()
    monkeypatch.setenv("SINGULAR_WEATHER_API", "http://example.com")
    monkeypatch.setenv("SINGULAR_HTTP_TIMEOUT", "0.1")

    def slow_get(url, timeout):
        time.sleep(timeout)
        raise Exception("timeout")

    fake_requests = types.SimpleNamespace(get=slow_get)
    monkeypatch.setitem(sys.modules, "requests", fake_requests)

    start = time.time()
    signals = capture_signals()
    duration = time.time() - start

    assert duration < 0.5
    assert "weather" not in signals


def test_capture_signals_publishes_normalized_artifact_events(tmp_path):
    reset_perception_state()
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    code = sandbox / "service.py"
    code.write_text("# FIXME: remove this hack\n", encoding="utf-8")
    log_file = sandbox / "service.log"
    log_file.write_text("first\n", encoding="utf-8")

    bus = EventBus(mode="sync")
    captured = []
    bus.subscribe("artifact.perception", lambda event: captured.append(event))

    # prime state to allow detecting modifications/new logs during second scan
    capture_signals(bus=bus, sandbox_root=sandbox)
    time.sleep(0.02)
    code.write_text("# FIXME: remove this hack\nprint('ok')\n", encoding="utf-8")
    signals = capture_signals(bus=bus, sandbox_root=sandbox)

    assert any(evt.payload["event"]["type"] == "artifact.files.modified" for evt in captured)
    assert any(evt.payload["event"]["type"] == "artifact.logs.new" for evt in captured)
    assert any(evt.payload["event"]["type"] == "artifact.tech_debt.simple" for evt in captured)

    for event in captured:
        assert event.payload_version == 1
        payload = event.payload
        assert payload["version"] == "1.0"
        normalized = payload["event"]
        assert set(normalized) >= {"type", "source", "confidence", "timestamp"}

    assert "artifact_events" in signals


def test_capture_signals_integrates_host_metrics_and_publishes_host_events(tmp_path, monkeypatch):
    reset_perception_state()

    monkeypatch.setattr(
        "singular.perception.collect_host_metrics",
        lambda: {
            "cpu_percent": 95.0,
            "cpu_load_1m": 4.0,
            "ram_used_percent": 95.0,
            "ram_available_mb": 512.0,
            "disk_used_percent": 97.0,
            "disk_free_gb": 100.0,
            "host_temperature_c": 86.0,
            "process_cpu_percent": 40.0,
            "process_rss_mb": 128.0,
        },
    )

    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    (sandbox / "app.py").write_text("print('ok')\n", encoding="utf-8")

    bus = EventBus(mode="sync")
    captured = []
    bus.subscribe("host.perception", lambda event: captured.append(event))

    signals = capture_signals(bus=bus, sandbox_root=sandbox)

    assert "host_metrics" in signals
    assert signals["host_metrics"]["cpu_percent"] == 95.0
    assert "host_events" in signals
    event_types = {event["type"] for event in signals["host_events"]}
    assert {
        "host.cpu.critical",
        "host.memory.critical",
        "host.thermal.critical",
        "host.disk.critical",
    }.issubset(event_types)

    assert any(evt.payload["event"]["type"] == "host.cpu.critical" for evt in captured)
    assert any(evt.payload["event"]["type"] == "host.memory.critical" for evt in captured)
    assert any(evt.payload["event"]["type"] == "host.thermal.critical" for evt in captured)
    assert any(evt.payload["event"]["type"] == "host.disk.critical" for evt in captured)

    for event in captured:
        payload = event.payload["event"]
        assert set(payload) >= {"type", "source", "confidence", "timestamp"}


def test_capture_signals_skips_host_metrics_when_sensor_unavailable(monkeypatch):
    reset_perception_state()

    def _boom():
        raise RuntimeError("sensor unavailable")

    monkeypatch.setattr("singular.perception.collect_host_metrics", _boom)

    signals = capture_signals()

    assert "host_metrics" not in signals
