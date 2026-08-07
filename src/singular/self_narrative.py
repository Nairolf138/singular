"""Versioned persistent self-narrative memory."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
import json
import hashlib

from singular.identity.coherence import detect_contradictions
from singular.io_utils import append_jsonl_line, atomic_write_text

SCHEMA_VERSION = 3
TIMELINE_SUFFIX = ".timeline.jsonl"

_TRAIT_KEYS = ("curiosity", "patience", "playfulness", "optimism", "resilience")


@dataclass
class IdentitySummary:
    """Condensed identity metadata."""

    name: str = "Singular"
    born_at: str = ""
    logical_age: int = 0


@dataclass
class LifePeriod:
    """A notable period in life history."""

    title: str
    start_at: str | None = None
    end_at: str | None = None
    highlights: list[str] = field(default_factory=list)


@dataclass
class TraitTrend:
    """Trend information for one trait."""

    value: float = 0.5
    trend: str = "stable"


@dataclass
class RegretsAndPride:
    """Meaningful wins, losses and costs."""

    significant_successes: list[str] = field(default_factory=list)
    significant_failures: list[str] = field(default_factory=list)
    abandoned_skills: list[str] = field(default_factory=list)
    costly_incidents: list[str] = field(default_factory=list)


@dataclass
class NarrativeEntry:
    """One attributable, causal and explicitly qualified story statement."""

    entry_id: str
    life_id: str
    event_type: str
    occurred_at: str
    summary: str
    source_event_ids: list[str] = field(default_factory=list)
    objective_ids: list[str] = field(default_factory=list)
    participants: list[str] = field(default_factory=list)
    confidence: float = 1.0
    change_type: str = "observation"
    causal_links: list[dict[str, str]] = field(default_factory=list)
    certainty: str = "certain"
    contradictions: list[dict[str, str]] = field(default_factory=list)


@dataclass
class SelfNarrative:
    """Persistent self narrative with explicit schema version."""

    schema_version: int
    identity: IdentitySummary
    life_periods: list[LifePeriod]
    trait_trends: dict[str, TraitTrend]
    regrets_and_pride: RegretsAndPride
    current_heading: str
    objective_trends: dict[str, TraitTrend] = field(default_factory=dict)
    life_id: str = "default"
    entries: list[NarrativeEntry] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["trait_trends"] = {
            key: asdict(value) for key, value in self.trait_trends.items()
        }
        payload["objective_trends"] = {
            key: asdict(value) for key, value in self.objective_trends.items()
        }
        payload["entries"] = [asdict(entry) for entry in self.entries]
        return payload


def extract_planner_signals(narrative: SelfNarrative | None = None) -> dict[str, Any]:
    """Extract planner-ready narrative signals from the persistent story."""

    current = narrative or load()
    regrets = current.regrets_and_pride
    failures = len(regrets.significant_failures)
    incidents = len(regrets.costly_incidents)
    successes = len(regrets.significant_successes)
    abandoned = len(regrets.abandoned_skills)
    drift = sum(
        1 for trend in current.trait_trends.values() if trend.trend in {"up", "down"}
    )
    coherence = max(
        0.0,
        min(
            1.0,
            1.0
            - (
                (failures + incidents + abandoned)
                / max(1.0, successes + failures + 1.0)
            ),
        ),
    )
    regret_pressure = max(0.0, min(1.0, (failures + incidents + abandoned) / 12.0))
    pride_drive = max(0.0, min(1.0, successes / 12.0))
    identity_drift = max(0.0, min(1.0, drift / max(1.0, len(current.trait_trends))))
    dissonance = max(
        0.0, min(1.0, regret_pressure * 0.6 + identity_drift * 0.4 - pride_drive * 0.3)
    )
    return {
        "coherence_signal": coherence,
        "regret_pressure": regret_pressure,
        "pride_drive": pride_drive,
        "identity_drift": identity_drift,
        "dissonance_signal": dissonance,
        "counts": {
            "successes": successes,
            "failures": failures,
            "abandoned": abandoned,
            "incidents": incidents,
        },
    }


def _default_trait_trends() -> dict[str, TraitTrend]:
    return {key: TraitTrend() for key in _TRAIT_KEYS}


def _default_narrative() -> SelfNarrative:
    return SelfNarrative(
        schema_version=SCHEMA_VERSION,
        identity=IdentitySummary(),
        life_periods=[],
        trait_trends=_default_trait_trends(),
        regrets_and_pride=RegretsAndPride(),
        current_heading="Clarifier ma prochaine étape utile.",
        objective_trends={},
        life_id="default",
        entries=[],
    )


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _compute_logical_age(born_at: str | None, now: datetime | None = None) -> int:
    born = _parse_iso(born_at)
    if born is None:
        return 0
    if born.tzinfo is None:
        born = born.replace(tzinfo=timezone.utc)
    current = now or datetime.now(timezone.utc)
    delta = current - born
    if delta.total_seconds() <= 0:
        return 0
    return int(delta.days)


def _coerce_trend(value: str | None) -> str:
    if value in {"up", "down", "stable"}:
        return value
    return "stable"


def _coerce_float(value: Any, default: float = 0.5) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, numeric))


def _path_or_default(path: Path | str | None) -> Path:
    if path is not None:
        return Path(path)
    return Path("mem") / "self_narrative.json"


def timeline_path(path: Path | str | None = None) -> Path:
    """Return the append-only timeline belonging to a narrative projection."""

    current = _path_or_default(path)
    return current.with_name(current.stem + TIMELINE_SUFFIX)


def load_snapshots(path: Path | str | None = None) -> list[dict[str, Any]]:
    """Read valid snapshots without letting a damaged line hide later history."""

    return sorted(
        _load_timeline_records(path), key=lambda item: str(item["recorded_at"])
    )


def _load_timeline_records(path: Path | str | None = None) -> list[dict[str, Any]]:
    """Read timeline records in append order, independently of wall-clock drift."""

    snapshots: list[dict[str, Any]] = []
    try:
        lines = timeline_path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return snapshots
    for line in lines:
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict) and _parse_iso(item.get("recorded_at")):
            snapshots.append(item)
    return snapshots


def infer_trend(
    observations: Sequence[tuple[datetime, float]],
    *,
    now: datetime,
    window: timedelta = timedelta(days=7),
    minimum_observations: int = 3,
    minimum_delta: float = 0.03,
) -> str:
    """Infer a bounded linear trend from sufficiently dense recent evidence."""

    recent = sorted(
        ((at, value) for at, value in observations if now - window <= at <= now),
        key=lambda item: item[0],
    )
    if len(recent) < minimum_observations:
        return "stable"
    xs = [(at - recent[0][0]).total_seconds() / 86400 for at, _ in recent]
    ys = [value for _, value in recent]
    mean_x, mean_y = sum(xs) / len(xs), sum(ys) / len(ys)
    denominator = sum((x - mean_x) ** 2 for x in xs)
    if denominator == 0:
        return "stable"
    projected_delta = (
        sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
        / denominator
        * max(xs[-1] - xs[0], 1.0)
    )
    return (
        "up"
        if projected_delta >= minimum_delta
        else "down" if projected_delta <= -minimum_delta else "stable"
    )


def _materialize(payload: Mapping[str, Any]) -> SelfNarrative:
    schema_version = int(payload.get("schema_version", 0) or 0)
    identity_payload = (
        payload.get("identity") if isinstance(payload.get("identity"), Mapping) else {}
    )
    born_at = identity_payload.get("born_at")

    identity = IdentitySummary(
        name=str(identity_payload.get("name", "Singular")),
        born_at=str(born_at) if born_at else "",
        logical_age=int(identity_payload.get("logical_age", 0) or 0),
    )

    life_periods: list[LifePeriod] = []
    raw_periods = payload.get("life_periods")
    if isinstance(raw_periods, list):
        for item in raw_periods:
            if not isinstance(item, Mapping):
                continue
            highlights = item.get("highlights")
            life_periods.append(
                LifePeriod(
                    title=str(item.get("title", "Période")),
                    start_at=(
                        str(item.get("start_at")) if item.get("start_at") else None
                    ),
                    end_at=str(item.get("end_at")) if item.get("end_at") else None,
                    highlights=(
                        [str(h) for h in highlights]
                        if isinstance(highlights, list)
                        else []
                    ),
                )
            )

    trait_trends = _default_trait_trends()
    raw_traits = payload.get("trait_trends")
    if isinstance(raw_traits, Mapping):
        for key in _TRAIT_KEYS:
            current = raw_traits.get(key)
            if isinstance(current, Mapping):
                trait_trends[key] = TraitTrend(
                    value=_coerce_float(
                        current.get("value"), default=trait_trends[key].value
                    ),
                    trend=_coerce_trend(
                        current.get("trend") if isinstance(current, Mapping) else None
                    ),
                )

    regrets_payload = (
        payload.get("regrets_and_pride")
        if isinstance(payload.get("regrets_and_pride"), Mapping)
        else {}
    )
    regrets = RegretsAndPride(
        significant_successes=[
            str(value)
            for value in regrets_payload.get("significant_successes", [])
            if isinstance(regrets_payload.get("significant_successes"), list)
        ],
        significant_failures=[
            str(value)
            for value in regrets_payload.get("significant_failures", [])
            if isinstance(regrets_payload.get("significant_failures"), list)
        ],
        abandoned_skills=[
            str(value)
            for value in regrets_payload.get("abandoned_skills", [])
            if isinstance(regrets_payload.get("abandoned_skills"), list)
        ],
        costly_incidents=[
            str(value)
            for value in regrets_payload.get("costly_incidents", [])
            if isinstance(regrets_payload.get("costly_incidents"), list)
        ],
    )

    entries: list[NarrativeEntry] = []
    raw_entries = payload.get("entries")
    if isinstance(raw_entries, list):
        for item in raw_entries:
            if not isinstance(item, Mapping):
                continue
            entries.append(
                NarrativeEntry(
                    entry_id=str(item.get("entry_id", "")),
                    life_id=str(item.get("life_id", payload.get("life_id", "default"))),
                    event_type=str(item.get("event_type", "unknown")),
                    occurred_at=str(item.get("occurred_at", "")),
                    summary=str(item.get("summary", "")),
                    source_event_ids=_string_list(item.get("source_event_ids")),
                    objective_ids=_string_list(item.get("objective_ids")),
                    participants=_string_list(item.get("participants")),
                    confidence=_coerce_float(item.get("confidence"), 1.0),
                    change_type=str(item.get("change_type", "observation")),
                    causal_links=(
                        [
                            {str(k): str(v) for k, v in link.items()}
                            for link in item.get("causal_links", [])
                            if isinstance(link, Mapping)
                        ]
                        if isinstance(item.get("causal_links"), list)
                        else []
                    ),
                    certainty=str(item.get("certainty", "certain")),
                    contradictions=(
                        [
                            dict(value)
                            for value in item.get("contradictions", [])
                            if isinstance(value, Mapping)
                        ]
                        if isinstance(item.get("contradictions"), list)
                        else []
                    ),
                )
            )

    narrative = SelfNarrative(
        schema_version=max(schema_version, SCHEMA_VERSION),
        identity=identity,
        life_periods=life_periods,
        trait_trends=trait_trends,
        regrets_and_pride=regrets,
        current_heading=str(
            payload.get("current_heading", "Clarifier ma prochaine étape utile.")
        ),
        objective_trends={
            str(key): TraitTrend(
                value=_coerce_float(value.get("value")),
                trend=_coerce_trend(value.get("trend")),
            )
            for key, value in (
                payload.get("objective_trends", {}).items()
                if isinstance(payload.get("objective_trends"), Mapping)
                else []
            )
            if isinstance(value, Mapping)
        },
        life_id=str(payload.get("life_id", "default")),
        entries=entries,
    )
    narrative.identity.logical_age = _compute_logical_age(narrative.identity.born_at)
    return narrative


def _migrate(payload: Mapping[str, Any]) -> SelfNarrative:
    """Soft migration from older/partial payloads to current schema."""

    narrative = _materialize(payload)
    if narrative.schema_version < SCHEMA_VERSION:
        narrative.schema_version = SCHEMA_VERSION
    return narrative


def load(path: Path | str | None = None) -> SelfNarrative:
    """Load narrative from disk with graceful fallback for missing/corrupt file."""

    file_path = _path_or_default(path)
    if not file_path.exists():
        narrative = _default_narrative()
        save(narrative, file_path, record_snapshot=False)
        return narrative

    try:
        payload = json.loads(file_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        backup = file_path.with_suffix(
            file_path.suffix + f".corrupt-{int(datetime.now(timezone.utc).timestamp())}"
        )
        try:
            file_path.rename(backup)
        except OSError:
            pass
        narrative = rebuild_from_timeline(file_path, persist=False)
        save(narrative, file_path, record_snapshot=False)
        return narrative

    if not isinstance(payload, Mapping):
        narrative = _default_narrative()
        save(narrative, file_path, record_snapshot=False)
        return narrative

    narrative = _migrate(payload)
    save(narrative, file_path, record_snapshot=False)
    return narrative


def save(
    narrative: SelfNarrative,
    path: Path | str | None = None,
    *,
    clock: Callable[[], datetime] | None = None,
    record_snapshot: bool = True,
    snapshot_metadata: Mapping[str, Any] | None = None,
) -> SelfNarrative:
    """Persist narrative JSON and return canonicalized object."""

    file_path = _path_or_default(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    narrative.schema_version = SCHEMA_VERSION
    narrative.identity.logical_age = _compute_logical_age(narrative.identity.born_at)
    atomic_write_text(
        file_path,
        json.dumps(narrative.to_dict(), ensure_ascii=False, indent=2),
    )
    if record_snapshot:
        now = (clock or (lambda: datetime.now(timezone.utc)))()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        snapshot = {
            "recorded_at": now.astimezone(timezone.utc).isoformat(),
            "schema_version": SCHEMA_VERSION,
            "narrative": narrative.to_dict(),
            "metadata": dict(snapshot_metadata or {}),
        }
        history = timeline_path(file_path)
        history.parent.mkdir(parents=True, exist_ok=True)
        with history.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(snapshot, ensure_ascii=False) + "\n")
    return narrative


def _extend_unique(target: list[str], values: Any) -> None:
    if not isinstance(values, list):
        return
    for value in values:
        text = str(value).strip()
        if text and text not in target:
            target.append(text)


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [str(item) for item in value if str(item).strip()]


SIGNIFICANT_EVENT_TYPES = frozenset(
    {
        "birth",
        "goal",
        "conversation",
        "learning",
        "moral_decision",
        "relationship",
        "mutation",
        "incident",
        "life_transition",
    }
)
_EVENT_TYPE_ALIASES = {
    "born": "birth",
    "life.birth": "birth",
    "goal.created": "goal",
    "goal.updated": "goal",
    "conversation.message": "conversation",
    "learning.completed": "learning",
    "action.moral.decision": "moral_decision",
    "relationship.changed": "relationship",
    "mutation.applied": "mutation",
    "mutation.rejected": "mutation",
    "incident.detected": "incident",
    "life.transition": "life_transition",
    "vital.transition": "life_transition",
}


def _normalize_event_type(value: Any) -> str:
    raw = str(value or "").strip()
    return _EVENT_TYPE_ALIASES.get(raw, raw)


def _event_identifier(event: Mapping[str, Any]) -> str:
    explicit = event.get("event_id") or event.get("id")
    if explicit:
        return str(explicit)
    canonical = json.dumps(dict(event), ensure_ascii=False, sort_keys=True, default=str)
    return "event-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:20]


def _apply_entry(narrative: SelfNarrative, entry: NarrativeEntry) -> bool:
    if entry.life_id != narrative.life_id:
        return False
    if any(current.entry_id == entry.entry_id for current in narrative.entries):
        return False
    narrative.entries.append(entry)
    return True


def rebuild_from_timeline(
    path: Path | str | None = None,
    *,
    life_id: str | None = None,
    persist: bool = True,
) -> SelfNarrative:
    """Rebuild a projection from valid append-only records, skipping damage."""

    wanted_life = life_id
    narrative = _default_narrative()
    if wanted_life is not None:
        narrative.life_id = wanted_life
    for record in _load_timeline_records(path):
        projection = record.get("narrative")
        if isinstance(projection, Mapping) and not record.get("entry"):
            candidate = _migrate(projection)
            if wanted_life is None or candidate.life_id == wanted_life:
                narrative = candidate
            continue
        raw_entry = record.get("entry")
        if not isinstance(raw_entry, Mapping):
            continue
        record_life = str(raw_entry.get("life_id", "default"))
        if wanted_life is None and not narrative.entries:
            narrative.life_id = record_life
        if record_life != narrative.life_id:
            continue
        entry_payload = dict(raw_entry)
        temp = _materialize({"life_id": record_life, "entries": [entry_payload]})
        if temp.entries:
            _apply_entry(narrative, temp.entries[0])
        resulting = record.get("resulting_narrative")
        if isinstance(resulting, Mapping):
            candidate = _migrate(resulting)
            if candidate.life_id == narrative.life_id:
                narrative = candidate
    if persist:
        save(narrative, path, record_snapshot=False)
    return narrative


def project_event(
    event: Mapping[str, Any],
    path: Path | str | None = None,
    *,
    life_id: str = "default",
    autobiographical_facts: Sequence[Mapping[str, Any]] = (),
    commitments: Sequence[Mapping[str, Any]] = (),
    history: Sequence[Mapping[str, Any]] = (),
    clock: Callable[[], datetime] | None = None,
) -> SelfNarrative:
    """Incrementally project one significant event with provenance and coherence."""

    event_type = _normalize_event_type(event.get("event_type") or event.get("type"))
    if event_type not in SIGNIFICANT_EVENT_TYPES:
        raise ValueError(f"unsupported narrative event type: {event_type or 'missing'}")
    file_path = _path_or_default(path)
    projected = load(file_path)
    if projected.entries and projected.life_id != life_id:
        # A path is the storage boundary of one life; never mix identities.
        raise ValueError("narrative path belongs to a different life")
    narrative = (
        rebuild_from_timeline(file_path, life_id=life_id, persist=False)
        if timeline_path(file_path).exists()
        else projected
    )
    if narrative.entries and narrative.life_id != life_id:
        raise ValueError("narrative path belongs to a different life")
    narrative.life_id = life_id
    event_id = _event_identifier(event)
    if any(event_id in entry.source_event_ids for entry in narrative.entries):
        return narrative

    now = (clock or (lambda: datetime.now(timezone.utc)))()
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    summary = str(event.get("summary") or event.get("statement") or event_type).strip()
    contradictions = detect_contradictions(
        beliefs=[
            {"statement": summary},
            *[dict(item) for item in autobiographical_facts],
        ],
        goals=[dict(item) for item in commitments],
        history=[
            *[{"summary": entry.summary} for entry in narrative.entries],
            *[dict(item) for item in history],
        ],
    )
    certainty = (
        "uncertain" if contradictions else str(event.get("certainty", "certain"))
    )
    entry = NarrativeEntry(
        entry_id=str(event.get("entry_id") or f"narrative-{event_id}"),
        life_id=life_id,
        event_type=event_type,
        occurred_at=str(
            event.get("occurred_at") or now.astimezone(timezone.utc).isoformat()
        ),
        summary=summary,
        source_event_ids=list(
            dict.fromkeys([event_id, *_string_list(event.get("source_event_ids"))])
        ),
        objective_ids=_string_list(event.get("objective_ids") or event.get("goals")),
        participants=_string_list(event.get("participants")),
        confidence=_coerce_float(event.get("confidence"), 1.0),
        change_type=str(event.get("change_type", event_type)),
        causal_links=(
            [
                dict(link)
                for link in event.get("causal_links", [])
                if isinstance(link, Mapping)
            ]
            if isinstance(event.get("causal_links"), list)
            else []
        ),
        certainty=certainty,
        contradictions=contradictions,
    )
    _apply_entry(narrative, entry)

    # Contradictory claims remain visible evidence but cannot replace prior state.
    if not contradictions:
        if event_type == "birth":
            narrative.identity.name = str(event.get("name") or narrative.identity.name)
            narrative.identity.born_at = str(event.get("born_at") or entry.occurred_at)
        heading = event.get("current_heading")
        if isinstance(heading, str) and heading.strip():
            narrative.current_heading = heading.strip()

    record = {
        "recorded_at": now.astimezone(timezone.utc).isoformat(),
        "schema_version": SCHEMA_VERSION,
        "record_type": "narrative_event",
        "life_id": life_id,
        "entry": asdict(entry),
        "resulting_narrative": narrative.to_dict(),
    }
    append_jsonl_line(timeline_path(file_path), record)
    save(narrative, file_path, record_snapshot=False)
    return narrative


class NarrativeProjector:
    """Small event-consumer facade suitable for synchronous event buses."""

    def __init__(self, path: Path | str, *, life_id: str) -> None:
        self.path = Path(path)
        self.life_id = life_id

    def consume(self, event: Any) -> SelfNarrative:
        payload = dict(getattr(event, "payload", event))
        if getattr(event, "event_type", None):
            payload.setdefault("event_type", _normalize_event_type(event.event_type))
            payload.setdefault(
                "event_id",
                payload.get("event_id")
                or f"{event.event_type}:{getattr(event, 'emitted_at', '')}",
            )
        return project_event(payload, self.path, life_id=self.life_id)

    def subscribe(self, bus: Any) -> None:
        """Subscribe incremental projection to every known major bus event."""

        for event_type in _EVENT_TYPE_ALIASES:
            bus.subscribe(event_type, self.consume)


def update_from_signals(
    signals: Mapping[str, Any],
    path: Path | str | None = None,
    *,
    clock: Callable[[], datetime] | None = None,
) -> SelfNarrative:
    """Update persisted narrative from external signals and return it."""

    narrative = load(path)

    identity_patch = signals.get("identity")
    if isinstance(identity_patch, Mapping):
        if "name" in identity_patch:
            narrative.identity.name = str(
                identity_patch.get("name") or narrative.identity.name
            )
        if "born_at" in identity_patch:
            narrative.identity.born_at = str(identity_patch.get("born_at") or "")

    current_heading = signals.get("current_heading")
    if isinstance(current_heading, str) and current_heading.strip():
        narrative.current_heading = current_heading.strip()

    periods = signals.get("life_periods")
    if isinstance(periods, list):
        for period in periods:
            if not isinstance(period, Mapping):
                continue
            narrative.life_periods.append(
                LifePeriod(
                    title=str(period.get("title", "Période")),
                    start_at=(
                        str(period.get("start_at")) if period.get("start_at") else None
                    ),
                    end_at=str(period.get("end_at")) if period.get("end_at") else None,
                    highlights=(
                        [str(x) for x in period.get("highlights", [])]
                        if isinstance(period.get("highlights"), list)
                        else []
                    ),
                )
            )

    trait_signals = signals.get("trait_trends")
    if isinstance(trait_signals, Mapping):
        for trait in _TRAIT_KEYS:
            patch = trait_signals.get(trait)
            if not isinstance(patch, Mapping):
                continue
            baseline = narrative.trait_trends[trait]
            baseline.value = _coerce_float(patch.get("value"), baseline.value)
            baseline.trend = _coerce_trend(patch.get("trend"))

    objective_signals = signals.get("objective_trends")
    if isinstance(objective_signals, Mapping):
        narrative.objective_trends = {
            str(name): TraitTrend(
                value=_coerce_float(patch.get("value")),
                trend=_coerce_trend(patch.get("trend")),
            )
            for name, patch in objective_signals.items()
            if isinstance(patch, Mapping)
        }

    regrets_signals = signals.get("regrets_and_pride")
    if isinstance(regrets_signals, Mapping):
        _extend_unique(
            narrative.regrets_and_pride.significant_successes,
            regrets_signals.get("significant_successes"),
        )
        _extend_unique(
            narrative.regrets_and_pride.significant_failures,
            regrets_signals.get("significant_failures"),
        )
        _extend_unique(
            narrative.regrets_and_pride.abandoned_skills,
            regrets_signals.get("abandoned_skills"),
        )
        _extend_unique(
            narrative.regrets_and_pride.costly_incidents,
            regrets_signals.get("costly_incidents"),
        )

    save(
        narrative,
        path,
        clock=clock,
        snapshot_metadata={
            "event_count": max(0, int(signals.get("event_count", 1))),
            "identity_transition": signals.get("identity_transition"),
        },
    )
    return narrative


def summarize_short(
    narrative: SelfNarrative | None = None, path: Path | str | None = None
) -> str:
    """Return a compact one-line summary."""

    current = narrative or load(path)
    return (
        f"{current.identity.name} · âge logique {current.identity.logical_age}j · "
        f"cap: {current.current_heading}"
    )


def summarize_long(
    narrative: SelfNarrative | None = None, path: Path | str | None = None
) -> str:
    """Return a richer human-readable summary."""

    current = narrative or load(path)
    traits = ", ".join(
        f"{name}={trend.value:.2f} ({trend.trend})"
        for name, trend in current.trait_trends.items()
    )
    periods = (
        "; ".join(period.title for period in current.life_periods[-3:])
        or "aucune période marquante"
    )

    wins = ", ".join(current.regrets_and_pride.significant_successes[-3:]) or "aucune"
    losses = ", ".join(current.regrets_and_pride.significant_failures[-3:]) or "aucune"
    dropped = ", ".join(current.regrets_and_pride.abandoned_skills[-3:]) or "aucune"
    incidents = ", ".join(current.regrets_and_pride.costly_incidents[-3:]) or "aucun"

    return (
        f"Identité: {current.identity.name} (né·e {current.identity.born_at or 'inconnu'}, "
        f"âge logique {current.identity.logical_age} jours).\n"
        f"Périodes marquantes: {periods}.\n"
        f"Traits: {traits}.\n"
        f"Fiertés: {wins}.\n"
        f"Regrets/échecs: {losses}.\n"
        f"Skills abandonnées: {dropped}.\n"
        f"Incidents coûteux: {incidents}.\n"
        f"Cap actuel: {current.current_heading}."
    )
