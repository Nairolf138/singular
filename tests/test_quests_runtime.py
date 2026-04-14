from __future__ import annotations

import json
from pathlib import Path

from singular.quests import QuestRuntime
from singular.resource_manager import ResourceManager


class DummyPsyche:
    def feel(self, _mood) -> None:
        return

    def gain(self, _amount: float) -> None:
        return

    def consume(self, _amount: float) -> None:
        return

    def save_state(self) -> None:
        return


def _write_quest(path: Path, *, name: str = "q-arb") -> None:
    path.write_text(
        json.dumps(
            {
                "name": name,
                "signature": "def solve(x): return x",
                "examples": [{"input": [1], "output": 1}],
                "constraints": {"pure": True, "no_import": True, "time_ms_max": 50},
                "triggers": [{"signal": "external_pressure", "gte": 0.5}],
                "reward": {"psyche_energy": 3},
                "penalty": {"psyche_energy": -4},
                "cooldown": 5,
                "success": {"resource_min": {"energy": 95}},
                "origin": "external",
            }
        ),
        encoding="utf-8",
    )


def test_objective_arbitration_pauses_then_resumes_and_tracks_history(tmp_path: Path) -> None:
    quests_dir = tmp_path / "quests"
    mem_dir = tmp_path / "mem"
    quests_dir.mkdir()
    mem_dir.mkdir()
    _write_quest(quests_dir / "q-arb.json")

    runtime = QuestRuntime(base_dir=tmp_path, mem_dir=mem_dir)
    activated = runtime.evaluate_triggers({"external_pressure": 0.8})
    assert activated == ["q-arb"]
    assert len(runtime.state.active) == 1

    psyche = DummyPsyche()
    resources = ResourceManager(path=tmp_path / "resources.json", energy=10, food=10, warmth=10)
    outcome = runtime.settle_active(
        psyche=psyche,
        resource_manager=resources,
        health_score=20.0,
        load_score=0.95,
    )
    assert outcome["paused"] == ["q-arb"]
    assert runtime.state.active == []
    assert len(runtime.state.paused) == 1
    assert runtime.state.paused[0].history[-1]["to"] == "paused"
    assert "objective_arbitration" in runtime.state.paused[0].history[-1]["reason"]

    resources.energy = 95
    resources.food = 95
    resources.warmth = 95
    outcome = runtime.settle_active(
        psyche=psyche,
        resource_manager=resources,
        health_score=90.0,
        load_score=0.1,
    )
    assert outcome["resumed"] == ["q-arb"]
    assert len(runtime.state.active) == 1
    transitions = [entry["to"] for entry in runtime.state.active[0].history[-3:]]
    assert "resumed" in transitions
    assert "active" in transitions


def test_objective_arbitration_can_abandon_after_repeated_pressure(tmp_path: Path) -> None:
    quests_dir = tmp_path / "quests"
    mem_dir = tmp_path / "mem"
    quests_dir.mkdir()
    mem_dir.mkdir()
    _write_quest(quests_dir / "q-arb.json")

    runtime = QuestRuntime(base_dir=tmp_path, mem_dir=mem_dir)
    runtime.evaluate_triggers({"external_pressure": 0.8})
    psyche = DummyPsyche()
    resources = ResourceManager(path=tmp_path / "resources.json", energy=12, food=12, warmth=12)

    record = runtime.state.active[0]
    record.history.extend(
        [
            {"at": "2026-01-01T00:00:00+00:00", "from": "active", "to": "paused", "reason": "prior_pressure"},
            {"at": "2026-01-01T00:01:00+00:00", "from": "paused", "to": "active", "reason": "prior_recovery"},
            {"at": "2026-01-01T00:02:00+00:00", "from": "active", "to": "paused", "reason": "prior_pressure"},
            {"at": "2026-01-01T00:03:00+00:00", "from": "paused", "to": "active", "reason": "prior_recovery"},
            {"at": "2026-01-01T00:04:00+00:00", "from": "active", "to": "paused", "reason": "prior_pressure"},
        ]
    )

    outcome = runtime.settle_active(
        psyche=psyche,
        resource_manager=resources,
        health_score=10.0,
        load_score=1.0,
    )
    assert outcome["abandoned"] == ["q-arb"]
    assert any(item.status == "abandoned" for item in runtime.state.completed)
    abandoned = next(item for item in runtime.state.completed if item.status == "abandoned")
    assert abandoned.history[-1]["to"] == "abandoned"
    assert abandoned.history[-1]["reason"] == "objective_arbitration_high_emotional_cost_or_risk"
