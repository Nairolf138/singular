from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from singular.life.social_decision import decide_social_actions
from singular.social.graph import SocialGraph
from singular.social.theory_of_mind import TheoryOfMindStore


def test_model_persists_after_restart(tmp_path: Path) -> None:
    path = tmp_path / "theory_of_mind.json"
    store = TheoryOfMindStore(path)
    first = store.observe("bob", "promise", intention="share", goal="cooperate")

    restarted = TheoryOfMindStore(path).get("bob")

    assert restarted["version"] == first["version"] == 1
    assert restarted["intentions"] == {"share": 0.58}
    assert restarted["supposed_goals"] == ["cooperate"]
    assert restarted["evidence"][0]["event"] == "promise"


def test_observed_result_revises_a_contradicted_intention(tmp_path: Path) -> None:
    store = TheoryOfMindStore(tmp_path / "theory_of_mind.json")
    promised = store.observe("bob", "promise", intention="share")
    contradicted = store.observe(
        "bob", "promise_broken", intention="share", outcome=False
    )

    assert contradicted["version"] == 2
    assert contradicted["intentions"]["share"] < promised["intentions"]["share"]
    assert contradicted["reliability"] < promised["reliability"]


def test_models_for_two_individuals_do_not_leak(tmp_path: Path) -> None:
    store = TheoryOfMindStore(tmp_path / "theory_of_mind.json")
    store.observe("alice", "cooperation", intention="help", outcome=True)
    store.observe("bob", "conflict", intention="compete", outcome=False)

    assert "help" in store.get("alice")["intentions"]
    assert "help" not in store.get("bob")["intentions"]
    assert store.get("alice")["reliability"] > store.get("bob")["reliability"]


def test_mental_model_has_measurable_effect_on_social_decision(tmp_path: Path) -> None:
    graph = SocialGraph(tmp_path / "social_graph.json")
    for _ in range(3):
        graph.update_relation("me", "bob", "successful_assistance")
    assert decide_social_actions("me", ["bob"], graph)[0].action == "help"

    for _ in range(3):
        graph.observe_mental_state(
            "bob", "promise_broken", intention="cooperate", outcome=False
        )
    decision = decide_social_actions("me", ["bob"], graph)[0]
    assert decision.action == "avoid"
    assert decision.reason == "predicted_unreliable_or_nonreciprocal"


def test_confidence_decays_and_sparse_evidence_is_cautious(tmp_path: Path) -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    store = TheoryOfMindStore(tmp_path / "theory_of_mind.json", clock=lambda: now)
    observed = store.observe("bob", "conversation", intention="help")
    later = TheoryOfMindStore(
        tmp_path / "theory_of_mind.json",
        clock=lambda: now + timedelta(days=30),
    ).get("bob")

    assert later["confidence"] == observed["confidence"] / 2
    graph = SocialGraph(tmp_path / "graph.json")
    graph.observe_mental_state("bob", "conversation", intention="help")
    decision = decide_social_actions("me", ["bob"], graph)[0]
    assert decision.reason == "insufficient_mental_state_evidence"
