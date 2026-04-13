from __future__ import annotations

import json
from pathlib import Path

from singular.beliefs.store import BeliefStore
from singular.life.loop import select_operator


def test_belief_store_updates_and_resets(tmp_path: Path) -> None:
    path = tmp_path / "beliefs.json"
    store = BeliefStore(path=path)

    rec1 = store.update_after_run(
        "operator:eq_rewrite_reduce_sum",
        success=True,
        evidence="accepted",
        reward_delta=0.12,
    )
    assert rec1.confidence > 0.5
    assert path.exists()

    rec2 = store.update_after_run(
        "operator:eq_rewrite_reduce_sum",
        success=False,
        evidence="rejected",
        reward_delta=-0.05,
    )
    assert rec2.runs == 2

    deleted = store.reset(hypothesis="operator:eq_rewrite_reduce_sum")
    assert deleted == 1
    assert store.list_beliefs() == []


def test_beliefs_bias_guides_operator_selection(tmp_path: Path) -> None:
    store = BeliefStore(path=tmp_path / "beliefs.json")
    for _ in range(5):
        store.update_after_run(
            "operator:preferred",
            success=True,
            evidence="ok",
            reward_delta=0.2,
        )
    for _ in range(5):
        store.update_after_run(
            "operator:other",
            success=False,
            evidence="ko",
            reward_delta=-0.2,
        )

    operators = {"preferred": lambda tree: tree, "other": lambda tree: tree}
    stats = {
        "preferred": {"count": 10, "reward": 0.0},
        "other": {"count": 10, "reward": 0.0},
    }
    selected = select_operator(
        operators,
        stats,
        policy="stochastic",
        rng=__import__("random").Random(0),
        objective_bias=store.operator_preference_bias(operators.keys()),
    )
    assert selected == "preferred"


def test_beliefs_file_is_json_serializable(tmp_path: Path) -> None:
    path = tmp_path / "beliefs.json"
    store = BeliefStore(path=path)
    store.update_after_run("operator:demo", success=True, evidence="ok")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert "operator:demo" in payload
