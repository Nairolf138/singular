from pathlib import Path

from singular.watch.daemon import InternalEventBus, WatchConfig, WatchDaemon


def test_watch_detects_file_change_and_persists_inbox(
    monkeypatch, tmp_path: Path
) -> None:
    life = tmp_path / "life"
    sensor = tmp_path / "sensor.txt"
    sensor.write_text("a", encoding="utf-8")

    monkeypatch.setenv("SINGULAR_HOME", str(life))
    monkeypatch.setenv("SINGULAR_SENSOR_FILE", str(sensor))

    bus = InternalEventBus()
    daemon = WatchDaemon(
        config=WatchConfig(
            interval_seconds=0.01,
            sources={"file"},
            dry_run=False,
        ),
        bus=bus,
    )

    assert daemon.tick() == []

    sensor.write_text("b", encoding="utf-8")
    changes = daemon.tick()

    assert changes
    assert bus.events
    assert bus.events[-1]["event_type"] == "watch.significant_change"

    inbox_path = life / "mem" / "inbox.json"
    assert inbox_path.exists()
    assert "watch" in inbox_path.read_text(encoding="utf-8")


def test_watch_dry_run_skips_inbox_persistence(monkeypatch, tmp_path: Path) -> None:
    life = tmp_path / "life"
    sensor = tmp_path / "sensor.txt"
    sensor.write_text("x", encoding="utf-8")

    monkeypatch.setenv("SINGULAR_HOME", str(life))
    monkeypatch.setenv("SINGULAR_SENSOR_FILE", str(sensor))

    daemon = WatchDaemon(
        config=WatchConfig(interval_seconds=0.01, sources={"file"}, dry_run=True)
    )

    daemon.tick()
    sensor.write_text("y", encoding="utf-8")
    daemon.tick()

    assert not (life / "mem" / "inbox.json").exists()
