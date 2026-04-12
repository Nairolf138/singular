import json

from singular.cli import main


def test_report_cli(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    runs = tmp_path / "runs"
    runs.mkdir()
    run_dir = runs / "run1"
    run_dir.mkdir()
    log = run_dir / "events.jsonl"
    records = [
        {
            "version": 1,
            "event_type": "mutation",
            "ts": "2026-01-01T00:00:00",
            "payload": {
                "op": "mutate",
                "score_new": 1.0,
                "human_summary": "op=mutate; fichier=a.py; acceptée; impact: score 2→1; perf ok",
                "decision_reason": "accepted: score improved",
            },
        },
        {
            "version": 1,
            "event_type": "mutation",
            "ts": "2026-01-01T00:00:01",
            "payload": {
                "op": "crossover",
                "score_new": 1.5,
                "human_summary": "op=crossover; fichier=a.py; rejetée; impact: score 1→1.5; perf slower",
                "decision_reason": "rejected: score regression",
            },
        },
    ]
    with log.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec) + "\n")
    mem = tmp_path / "mem"
    mem.mkdir()
    (mem / "skills.json").write_text(
        json.dumps({"skillA": {"score": 0.8}}), encoding="utf-8"
    )

    main(["report", "--id", "run1"])
    out = capsys.readouterr().out
    assert "Run run1" in out
    assert "Generations: 2" in out
    assert "Best score: 1.0" in out
    assert "skillA" in out


def test_report_records_include_explanatory_fields(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    runs = tmp_path / "runs"
    runs.mkdir()
    run_dir = runs / "run2"
    run_dir.mkdir()
    log = run_dir / "events.jsonl"
    log.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "version": 1,
                        "event_type": "mutation",
                        "ts": "2026-01-01T00:00:00",
                        "payload": {
                            "op": "mutate",
                            "score_new": 0.9,
                            "human_summary": "op=mutate; fichier=foo.py; acceptée; impact: score 1.0 → 0.9; perf: plus rapide",
                            "decision_reason": "accepted: score improved",
                        },
                    }
                )
            ]
        ),
        encoding="utf-8",
    )
    mem = tmp_path / "mem"
    mem.mkdir()
    (mem / "skills.json").write_text(json.dumps({}), encoding="utf-8")

    main(["report", "--id", "run2"])
    out = capsys.readouterr().out
    assert "Run run2" in out
    payload = json.loads(log.read_text(encoding="utf-8").splitlines()[0])["payload"]
    assert payload["human_summary"]
    assert "op=" in payload["human_summary"]
    assert payload["decision_reason"]
