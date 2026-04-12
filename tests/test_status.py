from __future__ import annotations

import json

import singular.organisms.status as status_mod


def test_status_displays_health_trend(tmp_path, monkeypatch, capsys) -> None:
    run_file = tmp_path / "demo.jsonl"
    with run_file.open("w", encoding="utf-8") as fh:
        for i in range(60):
            record = {
                "ok": True,
                "ms_new": 10.0 + i,
                "score_new": 1.0,
                "health": {"score": 30.0 + i},
            }
            fh.write(json.dumps(record) + "\n")

    class DummyPsyche:
        last_mood = None
        curiosity = 0.5
        patience = 0.5
        playfulness = 0.5
        optimism = 0.5
        resilience = 0.5

    monkeypatch.setattr(status_mod, "RUNS_DIR", tmp_path)
    monkeypatch.setattr(
        status_mod.Psyche, "load_state", staticmethod(lambda: DummyPsyche())
    )

    status_mod.status()
    out = capsys.readouterr().out
    assert "Health score:" in out
    assert "fenêtres 10/50" in out
