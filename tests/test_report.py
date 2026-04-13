import json
import os

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


def test_report_export_json_schema(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    runs = tmp_path / "runs"
    runs.mkdir()
    run_dir = runs / "run4"
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
                "score_new": 1.4,
                "decision_reason": "accepted",
            },
        },
        {
            "version": 1,
            "event_type": "mutation",
            "ts": "2026-01-01T00:00:01",
            "payload": {
                "op": "splice",
                "score_base": 1.4,
                "score_new": 1.2,
                "decision_reason": "accepted",
            },
        },
    ]
    with log.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec) + "\n")

    mem = tmp_path / "mem"
    mem.mkdir()
    (mem / "skills.json").write_text(json.dumps({"alpha": 1.0}), encoding="utf-8")

    export_path = tmp_path / "evolution.json"
    main(["report", "--id", "run4", "--export", str(export_path)])

    payload = json.loads(export_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["context"]["run_id"] == "run4"
    assert payload["summary"]["generations"] == 2
    assert payload["timeline"][0]["operator"] == "mutate"
    assert payload["timeline"][0]["verdict"] == "improvement"
    assert payload["verdict"] == "improvement"
    assert isinstance(payload["alerts"], list)
    assert payload["policy"]["active"]["version"] == 1
    assert isinstance(payload["policy"]["impact"], list)


def test_report_export_json_is_stable(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    runs = tmp_path / "runs"
    runs.mkdir()
    run_dir = runs / "run5"
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
                        },
                    }
                ),
                json.dumps(
                    {
                        "version": 1,
                        "event_type": "mutation",
                        "ts": "2026-01-01T00:00:01",
                        "payload": {
                            "op": "mutate",
                            "score_base": 0.9,
                            "score_new": 0.95,
                        },
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    mem = tmp_path / "mem"
    mem.mkdir()
    (mem / "skills.json").write_text(json.dumps({}), encoding="utf-8")

    export_path = tmp_path / "stable.json"
    main(["report", "--id", "run5", "--export", str(export_path)])
    content1 = export_path.read_text(encoding="utf-8")

    main(["report", "--id", "run5", "--export", str(export_path)])
    content2 = export_path.read_text(encoding="utf-8")

    assert content1 == content2


def test_report_export_markdown_stdout(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    runs = tmp_path / "runs"
    runs.mkdir()
    run_dir = runs / "run6"
    run_dir.mkdir()
    log = run_dir / "events.jsonl"
    log.write_text(
        json.dumps(
            {
                "version": 1,
                "event_type": "mutation",
                "ts": "2026-01-01T00:00:00",
                "payload": {
                    "op": "mutate",
                    "score_base": 1.0,
                    "score_new": 0.8,
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    mem = tmp_path / "mem"
    mem.mkdir()
    (mem / "skills.json").write_text("{}", encoding="utf-8")

    main(["report", "--id", "run6", "--export", "markdown"])
    out = capsys.readouterr().out
    assert "# Run report `run6`" in out
    assert "## Timeline des mutations" in out


def test_report_defaults_to_latest_run_when_id_missing(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    runs = tmp_path / "runs"
    runs.mkdir()

    run_old = runs / "run-old"
    run_old.mkdir()
    old_log = run_old / "events.jsonl"
    old_log.write_text(
        json.dumps(
            {
                "version": 1,
                "event_type": "mutation",
                "ts": "2026-01-01T00:00:00",
                "payload": {"op": "mutate", "score_base": 2.0, "score_new": 1.8},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    run_new = runs / "run-new"
    run_new.mkdir()
    new_log = run_new / "events.jsonl"
    new_log.write_text(
        json.dumps(
            {
                "version": 1,
                "event_type": "mutation",
                "ts": "2026-01-01T00:00:01",
                "payload": {"op": "splice", "score_base": 1.8, "score_new": 1.2},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    os.utime(old_log, (1, 1))
    os.utime(new_log, (2, 2))

    mem = tmp_path / "mem"
    mem.mkdir()
    (mem / "skills.json").write_text("{}", encoding="utf-8")

    main(["report"])
    out = capsys.readouterr().out
    assert "Run run-new" in out


def test_report_supports_subcommand_format_option(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    runs = tmp_path / "runs"
    runs.mkdir()
    run_dir = runs / "run-json"
    run_dir.mkdir()
    (run_dir / "events.jsonl").write_text(
        json.dumps(
            {
                "version": 1,
                "event_type": "mutation",
                "ts": "2026-01-01T00:00:00",
                "payload": {"op": "mutate", "score_base": 1.0, "score_new": 0.5},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    mem = tmp_path / "mem"
    mem.mkdir()
    (mem / "skills.json").write_text("{}", encoding="utf-8")

    main(["report", "--id", "run-json", "--format", "json"])
    out = capsys.readouterr().out.strip()
    payload = json.loads(out)
    assert payload["context"]["run_id"] == "run-json"
