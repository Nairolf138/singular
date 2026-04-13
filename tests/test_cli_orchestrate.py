from singular.cli import main


def test_cli_orchestrate_run_dispatches(monkeypatch, tmp_path) -> None:
    root = tmp_path / "root"
    main(["--root", str(root), "lives", "create", "--name", "Alpha"])

    captured: dict[str, object] = {}

    def fake_run_orchestrator_daemon(**kwargs):
        captured.update(kwargs)
        return 0

    monkeypatch.setattr(
        "singular.orchestrator.run_orchestrator_daemon",
        fake_run_orchestrator_daemon,
    )

    code = main(
        [
            "--root",
            str(root),
            "orchestrate",
            "run",
            "--veille-seconds",
            "0.5",
            "--action-seconds",
            "0.3",
            "--introspection-seconds",
            "0.2",
            "--sommeil-seconds",
            "0.8",
            "--poll-interval",
            "0.1",
            "--tick-budget",
            "0.05",
            "--dry-run",
        ]
    )

    assert code == 0
    assert captured["veille_seconds"] == 0.5
    assert captured["action_seconds"] == 0.3
    assert captured["introspection_seconds"] == 0.2
    assert captured["sommeil_seconds"] == 0.8
    assert captured["poll_interval_seconds"] == 0.1
    assert captured["tick_budget_seconds"] == 0.05
    assert captured["dry_run"] is True
