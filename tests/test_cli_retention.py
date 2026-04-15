from pathlib import Path

from singular.cli import main


def test_cli_retention_run_dry_run_dispatches(monkeypatch, tmp_path, capsys) -> None:
    root = tmp_path / "root"
    main(["--root", str(root), "lives", "create", "--name", "Alpha"])

    captured: dict[str, object] = {}

    class _Report:
        scope = "runs"
        decisions = ()

        @property
        def summary(self) -> dict[str, int]:
            return {"keep": 1, "delete": 0, "archive": 0}

    class _Outcome:
        executed = True
        report = _Report()
        skipped_reason = None
        minimum_interval_minutes = 15

    def fake_run_retention_service(**kwargs):
        captured.update(kwargs)
        return _Outcome()

    monkeypatch.setattr("singular.storage_retention.run_retention_service", fake_run_retention_service)

    code = main(["--root", str(root), "retention", "run", "--dry-run"])

    assert code == 0
    assert captured["dry_run"] is True
    assert captured["enforce_minimum_interval"] is False
    out = capsys.readouterr().out
    assert "planned_delete=0" in out


def test_cli_orchestrate_runs_startup_retention(monkeypatch, tmp_path) -> None:
    root = tmp_path / "root"
    main(["--root", str(root), "lives", "create", "--name", "Alpha"])

    called: dict[str, int] = {"retention": 0}

    class _Outcome:
        executed = True
        report = None
        skipped_reason = None
        minimum_interval_minutes = 15

    def fake_run_retention_service(**kwargs):
        called["retention"] += 1
        return _Outcome()

    def fake_run_orchestrator_daemon(**kwargs):
        called["orchestrator"] = 1
        return 0

    monkeypatch.setattr("singular.storage_retention.run_retention_service", fake_run_retention_service)
    monkeypatch.setattr(
        "singular.orchestrator.run_orchestrator_daemon",
        fake_run_orchestrator_daemon,
    )

    code = main(["--root", str(root), "orchestrate", "run"])

    assert code == 0
    assert called["retention"] == 1
    assert called["orchestrator"] == 1


def test_cli_retention_status_prints_usage(monkeypatch, tmp_path, capsys) -> None:
    root = tmp_path / "root"
    main(["--root", str(root), "lives", "create", "--name", "Alpha"])

    def fake_retention_status_snapshot(**kwargs):
        return {
            "usage": {
                "runs": {"size_mb": 1.5, "entries": [{"kind": "file", "name": "a.jsonl", "size_mb": 1.5}]},
                "mem": {"size_mb": 0.5, "entries": []},
                "lives": {"size_mb": 2.0, "entries": []},
            },
            "thresholds": {"max_runs": 20, "max_run_age_days": 30, "max_total_runs_size_mb": 512},
            "active_thresholds": {"max_runs": False, "max_total_runs_size_mb": True, "max_run_age_days": False},
            "last_purge": {"at": "2026-04-15T12:00:00+00:00", "summary": {"freed_mb": 3.5, "deleted": 7, "archived": 1}},
        }

    monkeypatch.setattr("singular.storage_retention.retention_status_snapshot", fake_retention_status_snapshot)

    code = main(["--root", str(root), "retention", "status"])

    assert code == 0
    out = capsys.readouterr().out
    assert "runs=1.50MB, mem=0.50MB, lives=2.00MB" in out
    assert "freed_mb=3.5, deleted=7, archived=1" in out
    assert "max_total_runs_size_mb" in out


def test_cli_retention_config_show_prints_active_thresholds(monkeypatch, tmp_path, capsys) -> None:
    root = tmp_path / "root"
    main(["--root", str(root), "lives", "create", "--name", "Alpha"])

    def fake_retention_status_snapshot(**kwargs):
        return {"thresholds": {"max_runs": 5, "max_run_age_days": 14, "max_total_runs_size_mb": 42}}

    monkeypatch.setattr("singular.storage_retention.retention_status_snapshot", fake_retention_status_snapshot)

    code = main(["--root", str(root), "retention", "config", "show"])

    assert code == 0
    out = capsys.readouterr().out
    assert '"max_runs": 5' in out
    assert '"max_run_age_days": 14' in out
