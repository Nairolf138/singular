"""OS perception pipeline producing raw and semantic events."""

from __future__ import annotations

from dataclasses import dataclass, field

from singular.core.agent_runtime import PerceptEvent

from .capture import BestEffortOSSnapshotProvider, OSSnapshotProvider
from .semantics import OSSemanticInterpreter


@dataclass
class OSPerceptionPipeline:
    """Collect OS snapshots and derive semantic context events."""

    source_name: str = "os.pipeline"
    provider: OSSnapshotProvider = field(default_factory=BestEffortOSSnapshotProvider)
    interpreter: OSSemanticInterpreter = field(default_factory=OSSemanticInterpreter)

    def collect(self) -> list[PerceptEvent]:
        snapshot = self.provider.collect_snapshot()
        semantic_events = self.interpreter.derive(snapshot)

        events = [
            PerceptEvent(
                event_type="os_state",
                source=self.source_name,
                payload=snapshot.to_payload(),
            )
        ]

        events.append(
            PerceptEvent(
                event_type="os_semantic",
                source=self.source_name,
                payload={
                    "observed_at": snapshot.observed_at,
                    "events": semantic_events,
                },
            )
        )

        return events
