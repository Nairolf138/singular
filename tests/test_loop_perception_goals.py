import random
from pathlib import Path

import singular.life.loop as life_loop
from singular.goals.intrinsic import GoalWeights
from singular.memory import read_causal_timeline


class _CaptureGoals:
    last_perception_signals = None
    last_skill_reputation = None

    def __init__(self, *args, **kwargs):
        pass

    def update_tick(self, *, tick, psyche, health_score, resources, perception_signals=None):
        _CaptureGoals.last_perception_signals = perception_signals
        return GoalWeights()

    def influence_action_hypotheses(self, hypotheses):
        return [
            {
                "action": h.action,
                "long_term": h.long_term,
                "sandbox_risk": h.sandbox_risk,
                "resource_cost": h.resource_cost,
            }
            for h in hypotheses
        ]

    def influence_operator_scores(self, operator_stats, skill_reputation=None):
        _CaptureGoals.last_skill_reputation = skill_reputation
        return {name: 0.0 for name in operator_stats}


def _dec_operator(tree, rng=None):
    return tree


def test_run_passes_capture_signals_to_intrinsic_goals(tmp_path: Path, monkeypatch) -> None:
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    (skills_dir / "foo.py").write_text("result = 1", encoding="utf-8")

    monkeypatch.setattr(life_loop, "IntrinsicGoals", _CaptureGoals)
    monkeypatch.setattr(
        life_loop,
        "capture_signals",
        lambda bus: {
            "noise": 0.8,
            "artifact_events": [
                {"type": "artifact.tech_debt.simple", "data": {"markers": 7}},
                {"type": "artifact.files.modified", "data": {"count": 2}},
            ],
        },
    )

    life_loop.run(
        skills_dir,
        tmp_path / "ckpt.json",
        budget_seconds=0.05,
        rng=random.Random(0),
        max_iterations=1,
        operators={"noop": _dec_operator},
    )

    assert _CaptureGoals.last_perception_signals is not None
    assert "artifact_events" in _CaptureGoals.last_perception_signals
    assert _CaptureGoals.last_perception_signals["artifact_events"][0]["type"] == "artifact.tech_debt.simple"
    assert isinstance(_CaptureGoals.last_skill_reputation, dict)
    traces = read_causal_timeline()
    assert traces
    last = traces[-1]
    assert last["pipeline"] == "life.loop"
    assert set(("input", "decision", "action", "result")).issubset(last)


def test_choose_skill_prioritizes_frequent_low_quality_skills(tmp_path: Path) -> None:
    org_dir = tmp_path / "org" / "skills"
    org_dir.mkdir(parents=True)
    low_quality = org_dir / "high_use_low_quality.py"
    low_quality.write_text("result = 1", encoding="utf-8")
    healthy = org_dir / "healthy.py"
    healthy.write_text("result = 1", encoding="utf-8")

    organisms = {"org": life_loop.Organism(org_dir)}
    reputation = {
        "high_use_low_quality": {
            "use_count": 12,
            "mean_quality": 0.2,
            "success_rate": 0.4,
            "recent_failures": 3,
        },
        "healthy": {
            "use_count": 4,
            "mean_quality": 0.8,
            "success_rate": 0.9,
            "recent_failures": 0,
        },
    }

    selections = [
        life_loop._choose_skill(
            random.Random(seed),
            organisms,
            skill_reputation=reputation,
        )[1].stem
        for seed in range(25)
    ]
    assert selections.count("high_use_low_quality") > selections.count("healthy")
