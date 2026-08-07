"""OS perception stack: raw host/app/input signals + semantic context events."""

from .capture import (
    ActiveWindowState,
    BestEffortOSSnapshotProvider,
    HostState,
    InputState,
    NotificationRecord,
    OSSnapshot,
    OSSnapshotProvider,
)
from .pipeline import OSPerceptionPipeline
from .semantics import OSSemanticInterpreter, SemanticRuleConfig

__all__ = [
    "ActiveWindowState",
    "BestEffortOSSnapshotProvider",
    "HostState",
    "InputState",
    "NotificationRecord",
    "OSPerceptionPipeline",
    "OSSemanticInterpreter",
    "OSSnapshot",
    "OSSnapshotProvider",
    "SemanticRuleConfig",
]
