from __future__ import annotations

import json
from pathlib import Path

from singular.life.social_decision import decide_social_actions
from singular.social.graph import SocialGraph


def test_social_graph_update_is_deterministic_and_persistent(tmp_path: Path) -> None:
    path = tmp_path / "mem" / "social_graph.json"
    graph = SocialGraph(path=path)

    updated = graph.update_relation("life-b", "life-a", "entraide_reussie")
    assert updated["affinity"] == 0.58
    assert updated["trust"] == 0.62
    assert updated["rivalry"] == 0.0
    assert len(updated["history"]) == 1

    reloaded = SocialGraph(path=path)
    relation = reloaded.get_relation("life-a", "life-b")
    assert relation["affinity"] == 0.58
    assert relation["trust"] == 0.62
    assert relation["rivalry"] == 0.0
    assert len(relation["history"]) == 1

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert "life-a::life-b" in payload["relations"]


def test_social_graph_clamps_values_and_trims_history(tmp_path: Path) -> None:
    graph = SocialGraph(path=tmp_path / "mem" / "social_graph.json")

    for _ in range(30):
        graph.update_relation("a", "b", "resource_conflict")

    relation = graph.get_relation("a", "b")
    assert relation["affinity"] == 0.0
    assert relation["trust"] < 0.5
    assert relation["rivalry"] == 1.0
    assert len(relation["history"]) == 20


def test_social_graph_rejects_unknown_events(tmp_path: Path) -> None:
    graph = SocialGraph(path=tmp_path / "mem" / "social_graph.json")

    try:
        graph.update_relation("a", "b", "unknown")
    except ValueError as exc:
        assert "Unsupported social event" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def _write_relation(path: Path, a: str, b: str, **values: float) -> SocialGraph:
    left, right = sorted((a, b))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "relations": {
                    f"{left}::{right}": {
                        "affinity": values.get("affinity", 0.5),
                        "trust": values.get("trust", 0.5),
                        "rivalry": values.get("rivalry", 0.0),
                        "history": [],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    return SocialGraph(path=path)


def test_social_decision_helps_when_trust_and_affinity_are_high(tmp_path: Path) -> None:
    graph = _write_relation(
        tmp_path / "mem" / "social_graph.json",
        "agent-a",
        "agent-b",
        affinity=0.82,
        trust=0.78,
        rivalry=0.2,
    )

    [decision] = decide_social_actions("agent-a", ["agent-b"], graph)

    assert decision.action == "help"
    assert decision.reason == "trust_and_affinity_high"


def test_social_decision_avoids_when_rivalry_is_high_and_trust_is_low(
    tmp_path: Path,
) -> None:
    graph = _write_relation(
        tmp_path / "mem" / "social_graph.json",
        "agent-a",
        "agent-b",
        affinity=0.82,
        trust=0.2,
        rivalry=0.86,
    )

    [decision] = decide_social_actions("agent-a", ["agent-b"], graph)

    assert decision.action == "avoid"
    assert decision.reason == "rivalry_high_trust_low"


def test_social_decision_competes_when_rivalry_is_high_but_trust_exists(
    tmp_path: Path,
) -> None:
    graph = _write_relation(
        tmp_path / "mem" / "social_graph.json",
        "agent-a",
        "agent-b",
        affinity=0.82,
        trust=0.55,
        rivalry=0.86,
    )

    [decision] = decide_social_actions("agent-a", ["agent-b"], graph)

    assert decision.action == "compete"
    assert decision.reason == "rivalry_high"
