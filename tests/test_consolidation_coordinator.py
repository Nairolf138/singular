from __future__ import annotations

import json
from pathlib import Path

from singular.identity.consolidation_coordinator import STAGES, ConsolidationCoordinator


def test_stage_checkpoints_resume_and_retry_idempotently(
    tmp_path: Path, monkeypatch
) -> None:
    coordinator = ConsolidationCoordinator(tmp_path)
    episodes = [{"id": "e1", "user_fact": "loves trees", "strategy": "reflect"}]
    original = coordinator._apply_stage
    failed = False

    def interrupt(stage, rows):
        nonlocal failed
        if stage == "metacognitive_self_model" and not failed:
            failed = True
            raise InterruptedError("power loss")
        return original(stage, rows)

    monkeypatch.setattr(coordinator, "_apply_stage", interrupt)
    first = coordinator.run(episodes)
    assert first["partial_errors"][0]["stage"] == "metacognitive_self_model"
    state = json.loads(coordinator.state_path.read_text())
    assert state["stages"]["autobiographical_memory"]["status"] == "completed"
    assert state["stages"]["metacognitive_self_model"]["status"] == "failed"

    second = coordinator.run([])  # resume from the durable pending batch
    assert second["partial_errors"] == []
    assert set(second["stages"]) == set(STAGES)
    audit = json.loads(coordinator.catalogue_path.read_text())
    semantic = [row for row in audit.values() if row["stage"] == "semantic_memory"]
    assert len(semantic) == 1
    assert semantic[0]["mentions"] == 1
    assert semantic[0]["provenance"] == ["e1"]


def test_retention_contradictions_and_critical_provenance(tmp_path: Path) -> None:
    coordinator = ConsolidationCoordinator(tmp_path)
    result = coordinator.run(
        [
            {
                "id": "critical",
                "user_fact": "is a parent",
                "importance": "critical",
                "obsolete": True,
            },
            {"id": "conflict", "user_fact": "not is a parent"},
            {"id": "old", "preference": "tea", "obsolete": True},
        ]
    )

    assert result["items_rejected"] >= 1
    assert result["items_forgotten"] >= 1
    audit = json.loads(coordinator.catalogue_path.read_text())
    critical = next(row for row in audit.values() if "critical" in row["provenance"])
    rejected = next(row for row in audit.values() if "conflict" in row["provenance"])
    forgotten = next(row for row in audit.values() if "old" in row["provenance"])
    assert critical["status"] == "active"
    assert critical["provenance"] == ["critical"]
    assert rejected["status"] == "rejected"
    assert forgotten["status"] == "forgotten"
