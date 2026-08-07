import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from singular.self_narrative import (
    NarrativeProjector,
    load,
    project_event,
    rebuild_from_timeline,
    timeline_path,
)


def _event(event_id: str, summary: str = "Je protège mes engagements.") -> dict:
    return {
        "event_id": event_id,
        "event_type": "moral_decision",
        "summary": summary,
        "objective_ids": ["coherence"],
        "participants": ["Nova", "Ada"],
        "confidence": 0.91,
        "change_type": "commitment_reinforced",
        "causal_links": [{"cause_event_id": "birth-1", "relation": "enabled"}],
    }


def test_reconstruction_preserves_provenance_across_restarts(tmp_path: Path) -> None:
    path = tmp_path / "nova" / "mem" / "self_narrative.json"
    project_event(_event("decision-1"), path, life_id="nova")
    restarted = NarrativeProjector(path, life_id="nova")
    restarted.consume(
        {
            "event_id": "learn-1",
            "event_type": "learning",
            "summary": "J'ai appris à vérifier.",
        }
    )

    rebuilt = rebuild_from_timeline(path, life_id="nova", persist=False)

    assert [entry.source_event_ids[0] for entry in rebuilt.entries] == [
        "decision-1",
        "learn-1",
    ]
    first = rebuilt.entries[0]
    assert first.objective_ids == ["coherence"]
    assert first.participants == ["Nova", "Ada"]
    assert first.confidence == 0.91
    assert first.change_type == "commitment_reinforced"
    assert first.causal_links[0]["cause_event_id"] == "birth-1"


def test_projection_is_idempotent_for_a_source_event(tmp_path: Path) -> None:
    path = tmp_path / "mem" / "self_narrative.json"
    project_event(_event("same"), path, life_id="nova")
    before = timeline_path(path).read_bytes()
    result = project_event(_event("same"), path, life_id="nova")

    assert len(result.entries) == 1
    assert timeline_path(path).read_bytes() == before


def test_contradiction_stays_uncertain_and_does_not_replace_heading(
    tmp_path: Path,
) -> None:
    path = tmp_path / "mem" / "self_narrative.json"
    project_event(
        {
            "event_id": "goal-1",
            "event_type": "goal",
            "summary": "protect users",
            "current_heading": "Protect users",
        },
        path,
        life_id="nova",
    )
    result = project_event(
        {
            "event_id": "goal-2",
            "event_type": "goal",
            "summary": "not protect users",
            "current_heading": "Ignore users",
        },
        path,
        life_id="nova",
        commitments=[{"name": "protect users"}],
    )

    assert result.current_heading == "Protect users"
    assert result.entries[-1].certainty == "uncertain"
    assert result.entries[-1].contradictions


def test_corrupt_projection_and_timeline_line_are_recoverable(tmp_path: Path) -> None:
    path = tmp_path / "mem" / "self_narrative.json"
    project_event(_event("safe"), path, life_id="nova")
    with timeline_path(path).open("a", encoding="utf-8") as handle:
        handle.write("{broken\n")
    path.write_text("{broken", encoding="utf-8")

    recovered = load(path)

    assert recovered.life_id == "nova"
    assert recovered.entries[0].source_event_ids == ["safe"]
    assert json.loads(path.read_text(encoding="utf-8"))["entries"]


def test_lives_are_separated_even_when_timeline_is_copied(tmp_path: Path) -> None:
    nova = tmp_path / "nova" / "self_narrative.json"
    ada = tmp_path / "ada" / "self_narrative.json"
    project_event(_event("nova-event"), nova, life_id="nova")
    ada.parent.mkdir(parents=True)
    timeline_path(ada).write_bytes(timeline_path(nova).read_bytes())

    rebuilt = rebuild_from_timeline(ada, life_id="ada", persist=False)

    assert rebuilt.life_id == "ada"
    assert rebuilt.entries == []
    with pytest.raises(ValueError, match="different life"):
        project_event(_event("ada-event"), nova, life_id="ada")


def test_continuity_over_multiple_restart_instances(tmp_path: Path) -> None:
    path = tmp_path / "mem" / "self_narrative.json"
    start = datetime(2026, 8, 1, tzinfo=timezone.utc)
    for index in range(4):
        projector = NarrativeProjector(path, life_id="nova")
        project_event(
            {
                "event_id": f"transition-{index}",
                "event_type": "life_transition",
                "summary": f"cycle {index}",
            },
            projector.path,
            life_id=projector.life_id,
            clock=lambda index=index: start + timedelta(days=index),
        )

    assert len(load(path).entries) == 4
    assert len(rebuild_from_timeline(path, life_id="nova", persist=False).entries) == 4
