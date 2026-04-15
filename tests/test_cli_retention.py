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
