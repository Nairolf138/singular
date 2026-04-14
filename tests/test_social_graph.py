from __future__ import annotations

import json
from pathlib import Path

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
