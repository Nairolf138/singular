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
