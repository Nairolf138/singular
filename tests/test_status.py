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


def test_status_verbose_displays_alerts(tmp_path, monkeypatch, capsys) -> None:
    run_file = tmp_path / "demo.jsonl"
    with run_file.open("w", encoding="utf-8") as fh:
        for i in range(12):
            record = {
                "ok": False,
                "accepted": False,
                "ms_new": 10.0,
                "score_new": 1.0,
                "health": {
                    "score": 70.0 - i,
                    "sandbox_stability": 0.95 - (i * 0.05),
                },
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

    status_mod.status(verbose=True)
    out = capsys.readouterr().out
    assert "Alerts:" in out
    assert "baisse continue du health score" in out


def test_status_filters_non_mutation_records_for_success_rate(
    tmp_path, monkeypatch, capsys
) -> None:
    run_file = tmp_path / "demo.jsonl"
    records = [
        {"event": "interaction", "ok": "yes", "ms_new": 1.0},
        {"event": "delay", "ms_new": 2.0},
        {"event": "death", "ok": None, "ms_new": 3.0},
        {"event": "mutation", "score_new": 1.0, "ok": True, "ms_new": 4.0},
        {"event": "mutation", "score_new": 1.2, "ok": False, "ms_new": 5.0},
        {"event": "mutation", "score_new": 1.3, "ms_new": 6.0},
        {"event": "interaction", "ok": True, "ms_new": 7.0},
    ]
    with run_file.open("w", encoding="utf-8") as fh:
        for record in records:
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

    status_mod.status(output_format="json")
    out = capsys.readouterr().out
    payload = json.loads(out)

    assert payload["mutation_count"] == 3
    assert payload["mutation_success_rate"] == 50.0
    assert payload["success_rate"] == 50.0
    assert payload["vital_timeline"]["age"] == 3
    assert payload["vital_timeline"]["state"] in {"mature", "declining", "terminal", "extinct"}
    assert "autonomy_metrics" in payload
    assert "proactive_initiative_rate" in payload["autonomy_metrics"]
    assert "host_environment" in payload
    assert "impact" in payload["host_environment"]


def test_status_exposes_quest_counts(tmp_path, monkeypatch, capsys) -> None:
    mem_dir = tmp_path / "mem"
    mem_dir.mkdir()
    (mem_dir / "quests_state.json").write_text(
        json.dumps(
            {
                "active": [{"name": "q1", "status": "active", "started_at": "2026-01-01T00:00:00+00:00"}],
                "paused": [{"name": "q2", "status": "paused", "started_at": "2026-01-01T00:00:00+00:00"}],
                "completed": [{"name": "q0", "status": "success", "started_at": "2026-01-01T00:00:00+00:00", "completed_at": "2026-01-01T00:01:00+00:00"}],
            }
        ),
        encoding="utf-8",
    )

    class DummyPsyche:
        last_mood = None
        curiosity = 0.5
        patience = 0.5
        playfulness = 0.5
        optimism = 0.5
        resilience = 0.5

    monkeypatch.setenv("SINGULAR_HOME", str(tmp_path))
    monkeypatch.setattr(status_mod, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(
        status_mod.Psyche, "load_state", staticmethod(lambda: DummyPsyche())
    )

    status_mod.status(output_format="json")
    payload = json.loads(capsys.readouterr().out)
    assert len(payload["quests"]["active"]) == 1
    assert len(payload["quests"]["paused"]) == 1
    assert len(payload["quests"]["completed"]) == 1
    assert payload["trajectory"]["objectives"]["counts"]["in_progress"] == 1
    assert payload["trajectory"]["objectives"]["counts"]["abandoned"] == 1
    assert payload["trajectory"]["objectives"]["counts"]["completed"] == 1


def test_status_exposes_trajectory_priority_and_narrative_links(
    tmp_path, monkeypatch, capsys
) -> None:
    run_file = tmp_path / "demo.jsonl"
    with run_file.open("w", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "ts": "2026-04-12T10:00:00+00:00",
                    "objective_weights": {"coherence": 0.4},
                }
            )
            + "\n"
        )
        fh.write(
            json.dumps(
                {
                    "ts": "2026-04-12T10:05:00+00:00",
                    "objective_weights": {"coherence": 0.7},
                    "event": "consciousness",
                    "objective": "coherence",
                }
            )
            + "\n"
        )

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

    status_mod.status(output_format="json")
    payload = json.loads(capsys.readouterr().out)
    assert payload["trajectory"]["priority_changes"]
    assert payload["trajectory"]["priority_changes"][0]["objective"] == "coherence"
    assert payload["trajectory"]["objective_narrative_links"]
    assert payload["trajectory"]["objective_narrative_links"][0]["objective"] == "coherence"


def test_status_exposes_skill_lifecycle_counts(tmp_path, monkeypatch, capsys) -> None:
    mem_dir = tmp_path / "mem"
    mem_dir.mkdir()
    (mem_dir / "skills.json").write_text(
        json.dumps(
            {
                "alpha": {"score": 0.1, "lifecycle": {"state": "active"}},
                "beta": {"score": 0.2, "lifecycle": {"state": "dormant"}},
                "gamma": {"score": 0.3, "lifecycle": {"state": "archived"}},
            }
        ),
        encoding="utf-8",
    )

    class DummyPsyche:
        last_mood = None
        curiosity = 0.5
        patience = 0.5
        playfulness = 0.5
        optimism = 0.5
        resilience = 0.5

    monkeypatch.setenv("SINGULAR_HOME", str(tmp_path))
    monkeypatch.setattr(status_mod, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(
        status_mod.Psyche, "load_state", staticmethod(lambda: DummyPsyche())
    )

    status_mod.status(output_format="json")
    payload = json.loads(capsys.readouterr().out)
    assert payload["skills_lifecycle"]["active"] == 1
    assert payload["skills_lifecycle"]["dormant"] == 1
    assert payload["skills_lifecycle"]["archived"] == 1
