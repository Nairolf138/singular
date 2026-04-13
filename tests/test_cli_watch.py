from pathlib import Path

from singular.cli import main


def test_cli_watch_dispatches_to_daemon(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path / "root"
    main(["--root", str(root), "lives", "create", "--name", "Alpha"])

    captured: dict[str, object] = {}

    def fake_run_watch_daemon(**kwargs):
        captured.update(kwargs)
        return 0

    monkeypatch.setattr("singular.watch.daemon.run_watch_daemon", fake_run_watch_daemon)

    code = main(
        [
            "--root",
            str(root),
            "watch",
            "--interval",
            "1.5",
            "--sources",
            "file,runs",
            "--cpu-budget",
            "35",
            "--memory-budget",
            "256",
            "--dry-run",
        ]
    )

    assert code == 0
    assert captured["interval_seconds"] == 1.5
    assert captured["sources"] == "file,runs"
    assert captured["cpu_budget_percent"] == 35
    assert captured["memory_budget_mb"] == 256
    assert captured["dry_run"] is True


def test_cli_veille_alias_dispatches(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path / "root"
    main(["--root", str(root), "lives", "create", "--name", "Alpha"])

    called = {"count": 0}

    def fake_run_watch_daemon(**_kwargs):
        called["count"] += 1
        return 0

    monkeypatch.setattr("singular.watch.daemon.run_watch_daemon", fake_run_watch_daemon)

    code = main(["--root", str(root), "veille"])

    assert code == 0
    assert called["count"] == 1
