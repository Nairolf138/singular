from __future__ import annotations

import json
from pathlib import Path

from singular.learning.curiosity import CuriosityEngine
from singular.learning.imitation import Demonstration, ImitationEngine


def _demo(name: str = "traffic") -> Demonstration:
    return Demonstration(
        observations=[{"light": "red"}, {"light": "green"}, {"light": "amber"}],
        actions=["stop", "go", "wait"],
        name=name,
    )


def test_imitation_improves_over_baseline_and_persists_curve(tmp_path: Path) -> None:
    engine = ImitationEngine(tmp_path)
    engine.ingest(_demo())
    outcome = engine.learn_next()
    engine.ingest(_demo())
    second_outcome = engine.learn_next()

    assert outcome is not None and outcome.status == "active"
    assert second_outcome is not None and second_outcome.status == "active"
    assert outcome.candidate_score > outcome.baseline_score
    curve = (tmp_path / "mem/learning/learning_curves.jsonl").read_text()
    assert '"score": 1.0' in curve
    assert '"episode": 2' in curve
    assert (tmp_path / "mem/skill_catalog.json").exists()


def test_dangerous_imitation_is_quarantined(tmp_path: Path) -> None:
    engine = ImitationEngine(tmp_path)
    outcome = engine.evaluate_and_publish(
        _demo("unsafe"),
        "import os\ndef run(observation):\n    return os.system('echo unsafe')\n",
    )

    assert outcome.status == "quarantined"
    assert not (tmp_path / "skills/unsafe.py").exists()
    assert list((tmp_path / "mem/learning/quarantine").glob("unsafe-*.py"))


def test_curiosity_limits_unproductive_exploration() -> None:
    curiosity = CuriosityEngine(budget=10, max_unproductive=2)
    score = curiosity.score(
        novelty=1,
        prediction_error=1,
        expected_information_gain=1,
        cost=0.1,
        risk=0,
        goal_relevance=1,
    )
    assert curiosity.authorize(score)
    curiosity.record_result(information_gain=0)
    curiosity.record_result(information_gain=0)
    assert not curiosity.authorize(score)


def test_pending_learning_resumes_after_restart(tmp_path: Path) -> None:
    first = ImitationEngine(tmp_path)
    first.ingest(_demo("resumed"))

    restarted = ImitationEngine(tmp_path)
    outcome = restarted.learn_next()

    assert outcome is not None and outcome.status == "active"
    state = json.loads((tmp_path / "mem/learning/state.json").read_text())
    assert state["pending"] == []
