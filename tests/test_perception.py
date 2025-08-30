import sys
import time
import types

from singular.perception import capture_signals
from singular.memory import add_episode, read_episodes


def test_capture_and_persist_signals(tmp_path, monkeypatch):
    # Prepare optional file sensor
    sensor_file = tmp_path / "sensor.txt"
    sensor_file.write_text("42", encoding="utf-8")
    monkeypatch.setenv("SINGULAR_SENSOR_FILE", str(sensor_file))

    # Capture signals
    signals = capture_signals()
    assert "temperature" in signals
    assert "is_daytime" in signals
    assert "noise" in signals
    assert signals.get("file") == "42"

    # Persist and verify
    episodic = tmp_path / "mem" / "episodic.jsonl"
    add_episode({"event": "perception", **signals}, path=episodic)
    episodes = read_episodes(path=episodic)
    assert episodes[0]["event"] == "perception"
    for key in ["temperature", "is_daytime", "noise", "file"]:
        assert key in episodes[0]


def test_weather_api_timeout(monkeypatch):
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
