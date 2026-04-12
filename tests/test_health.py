from __future__ import annotations

import json
from pathlib import Path

from singular.life.health import HealthTracker, detect_health_state
from singular.runs import report as report_mod


def test_health_tracker_progression() -> None:
    tracker = HealthTracker()
    scores: list[float] = []
    for i in range(1, 31):
        snap = tracker.update(
            iteration=i,
            latency_ms=350.0,
            accepted=False,
            sandbox_failure=True,
            energy=1.0,
            resources=1.0,
            failed=True,
        )
        scores.append(snap.score)
    for i in range(31, 91):
        snap = tracker.update(
            iteration=i,
            latency_ms=25.0,
            accepted=True,
            sandbox_failure=False,
            energy=4.5,
            resources=4.2,
            failed=False,
        )
        scores.append(snap.score)

    assert scores[-1] > 70.0
    assert detect_health_state(scores, short_window=10, long_window=50) == "amélioration"


def test_health_tracker_regression() -> None:
    tracker = HealthTracker()
    scores: list[float] = []
    for i in range(1, 51):
        scores.append(
            tracker.update(
                iteration=i,
                latency_ms=30.0,
                accepted=True,
                sandbox_failure=False,
                energy=4.0,
                resources=4.0,
                failed=False,
            ).score
        )
    for i in range(51, 101):
        scores.append(
            tracker.update(
                iteration=i,
                latency_ms=900.0,
                accepted=False,
                sandbox_failure=True,
                energy=0.2,
                resources=0.1,
                failed=True,
            ).score
        )

    assert scores[-1] < scores[49]
    assert detect_health_state(scores, short_window=10, long_window=50) == "dégradation"


def test_report_prints_health_state(tmp_path: Path, capsys) -> None:
    runs_dir = tmp_path / "runs"
    run_id = "demo"
    event_path = runs_dir / run_id / "events.jsonl"
    event_path.parent.mkdir(parents=True, exist_ok=True)
    for i in range(60):
        payload = {
            "op": "inc",
            "score_base": 2.0,
            "score_new": 1.0,
            "health": {"score": 40.0 + i},
        }
        event = {"event_type": "mutation", "payload": payload}
        with event_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event) + "\n")

    report_mod.report(run_id, runs_dir=runs_dir, skills_path=tmp_path / "skills.json")
    out = capsys.readouterr().out
    assert "Health:" in out
    assert "amélioration" in out
