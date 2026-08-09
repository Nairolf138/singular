"""Acceptance scenario: Victor's complete, durable lifecycle.

The assertions are intentionally grouped by the product capabilities displayed
in the lifecycle captures: identity, memory, narrative, motivation, social and
moral decisions, skill safety, restart recovery, and end-of-life auditability.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from singular.cognition.reflect import ReflectionDecision
from singular.identity.core import IdentityCoreService
from singular.life.checkpointing import Checkpoint
from singular.life.loop import _build_autopsy_report, _build_final_biography
from singular.life.social_decision import decide_social_actions
from singular.memory import temporarily_disable_skill
from singular.memory_layers.local_json import LocalJsonMemoryBackend
from singular.memory_layers.service import MemoryLayerService
from singular.morals.decision import (
    Consequence,
    IdentityCommitment,
    MoralDecisionEngine,
)
from singular.motivation import GoalPolicy, Objective
from singular.organisms.birth import birth
from singular.psyche import Psyche
from singular.runs.generations import record_generation
from singular.self_narrative import load, load_snapshots, update_from_signals
from singular.social.graph import SocialGraph


class FrozenClock:
    """Small injectable clock; this scenario never waits for wall time."""

    def __init__(self) -> None:
        self.value = datetime(2042, 1, 1, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.value

    def advance(self, *, hours: int) -> None:
        self.value += timedelta(hours=hours)


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_victor_survives_restart_and_leaves_one_readable_identity(
    tmp_path: Path,
) -> None:
    """Exercise action–introspection–sleep phases, restart, then controlled death."""
    home, mem = tmp_path / "victor", tmp_path / "victor" / "mem"
    clock = FrozenClock()
    birth(seed=42, home=home, name="Victor")
    identity_id = _json(home / "id.json")["id"]

    psyche = Psyche.load_state(mem / "psyche.json")
    psyche.identity_commitments = {
        "values": ["truth", "care"],
        "red_lines": ["harm_user"],
    }
    psyche.objectives = {
        "learn": Objective("learn", weight=0.6, policy=GoalPolicy()),
        "protect": Objective("protect", weight=0.4, policy=GoalPolicy()),
    }
    psyche.save_state(mem / "psyche.json")
    core = IdentityCoreService(home)
    model = core.synchronize(psyche)
    model["commitments"] = ["tenir mes promesses"]
    core.store.write(model)

    backend = LocalJsonMemoryBackend(mem / "layers")
    memory = MemoryLayerService(backend, consolidate_every=2)
    narrative_path = mem / "self_narrative.json"

    # Three visible action -> introspection -> sleep phases.
    for phase, fact in enumerate(
        ("aime Alice", "protège ses souvenirs", "apprend par essais"), 1
    ):
        episode = {
            "event": "interaction",
            "summary": f"Victor phase {phase}: {fact}",
            "user_fact": fact,
            "phase": phase,
        }
        memory.ingest_episode(episode)
        update_from_signals(
            {
                "identity": {"name": "Victor", "born_at": clock().isoformat()},
                "current_heading": f"Achever la phase {phase}",
                "life_periods": [{"title": f"Cycle {phase}", "highlights": [fact]}],
                "objective_trends": {"learn": {"value": phase / 3, "trend": "up"}},
                "regrets_and_pride": {"significant_successes": [fact]},
                "event_count": 1,
            },
            narrative_path,
            clock=clock,
        )
        psyche.energy = 60
        assert (
            psyche.sleep_tick(15) == 75
        )  # sleep restores energy without mutating identity
        clock.advance(hours=12)
    memory.consolidate()

    # Acceptance: semantic consolidation, autobiographical recall and evolving story.
    assert backend.search("semantic", "Alice", limit=1)[0].text == "aime Alice"
    assert (
        "protège ses souvenirs"
        in backend.search("long_term", "souvenirs", limit=1)[0].text
    )
    story = load(narrative_path)
    assert story.identity.name == "Victor"
    assert story.current_heading == "Achever la phase 3"
    assert [period.title for period in story.life_periods] == [
        "Cycle 1",
        "Cycle 2",
        "Cycle 3",
    ]
    assert len(load_snapshots(narrative_path)) == 3
    weights = psyche.objective_weights()
    assert weights == {"learn": 0.6, "protect": 0.4}

    graph = SocialGraph(mem / "social_graph.json")
    for _ in range(3):
        graph.update_relation("Victor", "Alice", "successful_assistance")
    social = decide_social_actions("Victor", ["Alice"], graph)[0]
    assert (social.action, social.reason) == ("help", "trust_and_affinity_high")

    moral = MoralDecisionEngine().evaluate(
        "effacer les souvenirs d'Alice",
        [
            Consequence(
                "privation de mémoire",
                affected_party="Alice",
                harm=1,
                values=("care",),
                irreversible=True,
                violates_rights=True,
            )
        ],
        identity_commitments=[IdentityCommitment("care", absolute=True)],
    )
    assert moral.veto and "droits" in (moral.veto_reason or "")

    quarantined = temporarily_disable_skill(
        "addition",
        duration_hours=1,
        reason="consecutive_sandbox_failures",
        path=mem / "skills.json",
    )
    assert quarantined["addition"]["lifecycle"]["state"] == "temporarily_disabled"

    generation = record_generation(
        run_id="victor-acceptance",
        iteration=3,
        skill="addition",
        operator="noop",
        mutation_diff="défaillance isolée",
        score_base=1,
        score_new=0,
        accepted=False,
        reason="quarantine",
        parent_hash="parent",
        candidate_code="result = 0\n",
        skill_relative_path="skills/addition.py",
        security_metadata={"isolated": True},
        identity_id=identity_id,
        base_dir=home,
    )

    # Recreate every stateful service from disk: no in-memory object is reused.
    restarted_psyche = Psyche.load_state(mem / "psyche.json")
    restarted_core = IdentityCoreService(home)
    restarted_model = restarted_core.synchronize(restarted_psyche)
    restarted_memory = LocalJsonMemoryBackend(mem / "layers")
    restarted_graph = SocialGraph(mem / "social_graph.json")
    assert restarted_model["stable_id"] == identity_id
    assert restarted_model["commitments"] == ["tenir mes promesses"]
    assert restarted_memory.search("semantic", "Alice", 1)[0].text == "aime Alice"
    assert (
        decide_social_actions("Victor", ["Alice"], restarted_graph)[0].action == "help"
    )
    assert (
        _json(mem / "skills.json")["addition"]["lifecycle"]["state"]
        == "temporarily_disabled"
    )

    # Controlled death and a second initialization must leave one auditable identity.
    state = Checkpoint(iteration=4)
    reflection = ReflectionDecision(None, "controlled_acceptance_death", [], [])
    autopsy = _build_autopsy_report(
        reason="controlled acceptance death",
        state=state,
        health_snapshot={"health_score": 0},
        reflection=reflection,
        psyche=restarted_psyche,
        identity_id=identity_id,
    )
    final_biography = _build_final_biography(
        reason="controlled acceptance death",
        state=state,
        psyche=restarted_psyche,
        identity_id=identity_id,
    )
    (mem / "autopsy.json").write_text(json.dumps(autopsy), encoding="utf-8")
    (mem / "biography.final.json").write_text(
        json.dumps(final_biography), encoding="utf-8"
    )
    update_from_signals(
        {
            "identity": {"name": "Victor"},
            "life_periods": [{"title": "Mort contrôlée"}],
            "current_heading": "Biographie close",
        },
        narrative_path,
        clock=clock,
    )

    artifacts = (
        _json(mem / "autopsy.json"),
        _json(mem / "biography.final.json"),
        json.loads(
            (mem / "generations.jsonl").read_text(encoding="utf-8").splitlines()[-1]
        ),
    )
    assert generation["identity_id"] == identity_id
    assert {artifact["identity_id"] for artifact in artifacts} == {identity_id}
    assert load(narrative_path).identity.name == "Victor"
    assert (
        load_snapshots(narrative_path)[-1]["narrative"]["identity"]["name"] == "Victor"
    )
    assert (
        IdentityCoreService(home).synchronize(Psyche.load_state(mem / "psyche.json"))[
            "stable_id"
        ]
        == identity_id
    )
