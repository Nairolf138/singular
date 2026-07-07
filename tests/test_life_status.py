from datetime import UTC, datetime

from singular.life.life_status import (
    AUTHORIZED_LIFE_STATUSES,
    LifeStatus,
    LifeStatusResult,
)


def test_authorized_life_statuses_are_stable_contract() -> None:
    assert AUTHORIZED_LIFE_STATUSES == (
        "not_alive_yet",
        "fragile",
        "alive",
        "dying",
        "extinct",
    )


def test_life_status_result_to_payload_serializes_portable_contract() -> None:
    computed_at = datetime(2026, 7, 7, 12, 30, tzinfo=UTC)
    result = LifeStatusResult(
        status=LifeStatus.ALIVE,
        score=0.91,
        explanation="Stable identity and cycle are observed.",
        signals={"stable_cycle": True, "observed_cycles": 4},
        missing_signals=("narrative_continuity",),
        evidence={"source": "test"},
        computed_at=computed_at,
    )

    assert result.to_payload() == {
        "status": "alive",
        "score": 0.91,
        "explanation": "Stable identity and cycle are observed.",
        "signals": {"stable_cycle": True, "observed_cycles": 4},
        "missing_signals": ["narrative_continuity"],
        "evidence": {"source": "test"},
        "computed_at": "2026-07-07T12:30:00+00:00",
    }
