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
                "score_base": 2.0,
                "score_new": 1.0,
                "human_summary": "op=mutate; fichier=a.py; acceptée; impact: score 2→1; perf ok",
                "decision_reason": "accepted: score improved",
                "loop_modifications": {
                    "lines_added": 3,
                    "lines_removed": 1,
                    "functions_modified": 1,
                    "ast_nodes_before": 20,
                    "ast_nodes_after": 24,
                },
            },
        },
        {
            "version": 1,
            "event_type": "mutation",
            "ts": "2026-01-01T00:00:01",
            "payload": {
                "op": "crossover",
                "score_base": 1.0,
                "score_new": 1.5,
                "human_summary": "op=crossover; fichier=a.py; rejetée; impact: score 1→1.5; perf slower",
                "decision_reason": "rejected: score regression",
                "loop_modifications": {
                    "lines_added": 1,
                    "lines_removed": 2,
                    "functions_modified": 1,
                    "ast_nodes_before": 24,
                    "ast_nodes_after": 22,
                },
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
    assert "Modifications de boucle:" in out


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
                            "score_base": 1.0,
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


def test_report_loop_modifications_ranking(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    runs = tmp_path / "runs"
    runs.mkdir()
    run_dir = runs / "run3"
    run_dir.mkdir()
    log = run_dir / "events.jsonl"
    records = [
        {
            "version": 1,
            "event_type": "mutation",
            "ts": "2026-01-01T00:00:00",
            "payload": {
                "op": "mutate",
                "score_base": 1.0,
                "score_new": 0.6,
                "loop_modifications": {
                    "lines_added": 2,
                    "lines_removed": 1,
                    "functions_modified": 1,
                    "ast_nodes_before": 10,
                    "ast_nodes_after": 12,
                },
            },
        },
        {
            "version": 1,
            "event_type": "mutation",
            "ts": "2026-01-01T00:00:01",
            "payload": {
                "op": "mutate",
                "score_base": 0.7,
                "score_new": 0.2,
                "loop_modifications": {
                    "lines_added": 5,
                    "lines_removed": 4,
                    "functions_modified": 2,
                    "ast_nodes_before": 12,
                    "ast_nodes_after": 18,
                },
            },
        },
        {
            "version": 1,
            "event_type": "mutation",
            "ts": "2026-01-01T00:00:02",
            "payload": {
                "op": "splice",
                "score_base": 0.2,
                "score_new": 0.15,
                "loop_modifications": {
                    "lines_added": 1,
                    "lines_removed": 1,
                    "functions_modified": 1,
                    "ast_nodes_before": 18,
                    "ast_nodes_after": 19,
                },
            },
        },
    ]
    with log.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec) + "\n")
    mem = tmp_path / "mem"
    mem.mkdir()
    (mem / "skills.json").write_text(json.dumps({}), encoding="utf-8")

    main(["report", "--id", "run3"])
    out = capsys.readouterr().out
    assert "Modifications de boucle:" in out
    assert "Plus gros changement:" in out
    assert "Plus fréquent:" in out
    assert "Plus rentable:" in out

    biggest_section = out.split("Plus gros changement:")[1].split("Plus fréquent:")[0]
    assert "#2 mutate" in biggest_section.splitlines()[1]

    frequent_section = out.split("Plus fréquent:")[1].split("Plus rentable:")[0]
    assert "mutate: 2" in frequent_section.splitlines()[1]

    profitable_section = out.split("Plus rentable:")[1]
    assert "#2 mutate" in profitable_section.splitlines()[1]
