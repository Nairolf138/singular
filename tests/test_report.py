import json

from singular.cli import main


def test_report_cli(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    runs = tmp_path / "runs"
    runs.mkdir()
    log = runs / "run1-000.jsonl"
    records = [
        {"op": "mutate", "score_new": 1.0},
        {"op": "crossover", "score_new": 1.5},
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
