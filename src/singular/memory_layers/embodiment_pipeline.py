"""Common projection pipeline for measured embodied action outcomes."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from singular.identity.consolidation_coordinator import ConsolidationCoordinator
from singular.self_narrative import update_from_signals

from .service import MemoryLayerService


class EmbodimentOutcomePipeline:
    """Deduplicate, consolidate and recall outcomes using causal provenance."""

    def __init__(
        self,
        memory: MemoryLayerService,
        coordinator: ConsolidationCoordinator,
        narrative_path: Path | str,
    ) -> None:
        self.memory = memory
        self.coordinator = coordinator
        self.narrative_path = Path(narrative_path)
        self._seen: set[str] = set()

    def consume(self, event: Any) -> dict[str, Any] | None:
        payload = getattr(event, "payload", event)
        if not isinstance(payload, Mapping):
            return None
        trace_id = str(payload.get("trace_id", ""))
        if not trace_id or trace_id in self._seen or payload.get("dry_run"):
            return None
        self._seen.add(trace_id)
        outcome = dict(payload)
        self.memory.ingest_embodied_outcome(outcome)
        self.coordinator.run([outcome])
        status = str(outcome.get("outcome_status", ""))
        summary = str(outcome.get("summary", ""))
        narrative_signals: dict[str, list[str]] = {}
        if status == "success":
            narrative_signals["significant_successes"] = [summary]
        elif status == "refused":
            narrative_signals["significant_failures"] = [summary]
        if outcome.get("costly"):
            narrative_signals["costly_incidents"] = [summary]
        update_from_signals(
            {"embodied_actions": [outcome], "regrets_and_pride": narrative_signals},
            self.narrative_path,
        )
        return outcome

    def decision_context(self, *, objective: str = "") -> dict[str, Any]:
        memories = self.memory.embodied_outcomes(objective=objective)
        return {
            "provenance": [row["provenance"] for row in memories],
            "outcomes": memories,
            "summary": " | ".join(str(row["summary"]) for row in memories),
        }
