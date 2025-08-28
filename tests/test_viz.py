import json
import viz


def test_viz_ascii(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    runs = tmp_path / "runs"
    runs.mkdir()
    log = runs / "r1-000.jsonl"
    records = [
        {"op": "mutate", "score_new": 1.0},
        {"op": "mutate", "score_new": 1.2},
    ]
    with log.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec) + "\n")
    viz.main(["--id", "r1", "--ascii"])
    out = capsys.readouterr().out
    assert "Generation 1" in out
    assert "mutate" in out
