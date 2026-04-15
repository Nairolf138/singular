from __future__ import annotations

from dataclasses import dataclass

from perception.os.capture import (
    ActiveWindowState,
    HostState,
    InputState,
    NotificationRecord,
    OSSnapshot,
    OSSnapshotProvider,
)
from perception.os.pipeline import OSPerceptionPipeline


@dataclass
class StaticSnapshotProvider(OSSnapshotProvider):
    snapshot: OSSnapshot

    def collect_snapshot(self) -> OSSnapshot:
        return self.snapshot


def test_os_pipeline_emits_raw_and_semantic_events() -> None:
    snapshot = OSSnapshot(
        observed_at="2026-04-15T00:00:00+00:00",
        active_window=ActiveWindowState(app="Zoom", title="Weekly Engineering Meeting"),
        input_state=InputState(mouse_x=120, mouse_y=88, keyboard_active=True, idle_seconds=1.5),
        notifications=[
            NotificationRecord(
                app="Calendar",
                title="Standup",
                body_preview="in 2 minutes",
                observed_at="2026-04-15T00:00:00+00:00",
            )
        ],
        host_state=HostState(
            network_online=True,
            network_type="wifi",
            battery_percent=14.0,
            battery_charging=False,
            cpu_percent=92.0,
        ),
    )

    pipeline = OSPerceptionPipeline(provider=StaticSnapshotProvider(snapshot=snapshot))

    events = pipeline.collect()

    assert len(events) == 2
    assert events[0].event_type == "os_state"
    assert events[0].payload["active_window"]["app"] == "Zoom"

    semantic = events[1]
    assert semantic.event_type == "os_semantic"
    semantic_types = {event["type"] for event in semantic.payload["events"]}
    assert "user.in_meeting" in semantic_types
    assert "host.cpu_high" in semantic_types
    assert "host.battery_low" in semantic_types
    assert "user.calendar_prompt" in semantic_types


def test_os_pipeline_detects_coding_window() -> None:
    snapshot = OSSnapshot(
        observed_at="2026-04-15T00:00:00+00:00",
        active_window=ActiveWindowState(app="Code", title="repo - main.py"),
        input_state=InputState(mouse_x=None, mouse_y=None, keyboard_active=False, idle_seconds=30.0),
        notifications=[],
        host_state=HostState(
            network_online=None,
            network_type=None,
            battery_percent=90.0,
            battery_charging=True,
            cpu_percent=15.0,
        ),
    )

    pipeline = OSPerceptionPipeline(provider=StaticSnapshotProvider(snapshot=snapshot))

    events = pipeline.collect()

    semantic_types = {event["type"] for event in events[1].payload["events"]}
    assert "workspace.coding_active" in semantic_types
    assert "host.battery_low" not in semantic_types
    assert "host.cpu_high" not in semantic_types
