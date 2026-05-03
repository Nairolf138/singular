"""Versioned persistent self-narrative memory."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
import json

SCHEMA_VERSION = 1

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
class SelfNarrative:
    """Persistent self narrative with explicit schema version."""

    schema_version: int
    identity: IdentitySummary
    life_periods: list[LifePeriod]
    trait_trends: dict[str, TraitTrend]
    regrets_and_pride: RegretsAndPride
    current_heading: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["trait_trends"] = {
            key: asdict(value) for key, value in self.trait_trends.items()
        }
        return payload


def extract_planner_signals(narrative: SelfNarrative | None = None) -> dict[str, Any]:
    """Extract planner-ready narrative signals from the persistent story."""

    current = narrative or load()
    regrets = current.regrets_and_pride
    failures = len(regrets.significant_failures)
    incidents = len(regrets.costly_incidents)
    successes = len(regrets.significant_successes)
    abandoned = len(regrets.abandoned_skills)
    drift = sum(1 for trend in current.trait_trends.values() if trend.trend in {"up", "down"})
    coherence = max(0.0, min(1.0, 1.0 - ((failures + incidents + abandoned) / max(1.0, successes + failures + 1.0))))
    regret_pressure = max(0.0, min(1.0, (failures + incidents + abandoned) / 12.0))
    pride_drive = max(0.0, min(1.0, successes / 12.0))
    identity_drift = max(0.0, min(1.0, drift / max(1.0, len(current.trait_trends))))
    dissonance = max(0.0, min(1.0, regret_pressure * 0.6 + identity_drift * 0.4 - pride_drive * 0.3))
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


def _materialize(payload: Mapping[str, Any]) -> SelfNarrative:
    schema_version = int(payload.get("schema_version", 0) or 0)
    identity_payload = payload.get("identity") if isinstance(payload.get("identity"), Mapping) else {}
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
                    start_at=str(item.get("start_at")) if item.get("start_at") else None,
                    end_at=str(item.get("end_at")) if item.get("end_at") else None,
                    highlights=[str(h) for h in highlights] if isinstance(highlights, list) else [],
                )
            )

    trait_trends = _default_trait_trends()
    raw_traits = payload.get("trait_trends")
    if isinstance(raw_traits, Mapping):
        for key in _TRAIT_KEYS:
            current = raw_traits.get(key)
            if isinstance(current, Mapping):
                trait_trends[key] = TraitTrend(
                    value=_coerce_float(current.get("value"), default=trait_trends[key].value),
                    trend=_coerce_trend(current.get("trend") if isinstance(current, Mapping) else None),
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

    narrative = SelfNarrative(
        schema_version=max(schema_version, SCHEMA_VERSION),
        identity=identity,
        life_periods=life_periods,
        trait_trends=trait_trends,
        regrets_and_pride=regrets,
        current_heading=str(payload.get("current_heading", "Clarifier ma prochaine étape utile.")),
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
        save(narrative, file_path)
        return narrative

    try:
        payload = json.loads(file_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        backup = file_path.with_suffix(file_path.suffix + f".corrupt-{int(datetime.now(timezone.utc).timestamp())}")
        try:
            file_path.rename(backup)
        except OSError:
            pass
        narrative = _default_narrative()
        save(narrative, file_path)
        return narrative

    if not isinstance(payload, Mapping):
        narrative = _default_narrative()
        save(narrative, file_path)
        return narrative

    narrative = _migrate(payload)
    save(narrative, file_path)
    return narrative


def save(narrative: SelfNarrative, path: Path | str | None = None) -> SelfNarrative:
    """Persist narrative JSON and return canonicalized object."""

    file_path = _path_or_default(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    narrative.schema_version = SCHEMA_VERSION
    narrative.identity.logical_age = _compute_logical_age(narrative.identity.born_at)
    file_path.write_text(
        json.dumps(narrative.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return narrative


def _extend_unique(target: list[str], values: Any) -> None:
    if not isinstance(values, list):
        return
    for value in values:
        text = str(value).strip()
        if text and text not in target:
            target.append(text)


def update_from_signals(
    signals: Mapping[str, Any], path: Path | str | None = None
) -> SelfNarrative:
    """Update persisted narrative from external signals and return it."""

    narrative = load(path)

    identity_patch = signals.get("identity")
    if isinstance(identity_patch, Mapping):
        if "name" in identity_patch:
            narrative.identity.name = str(identity_patch.get("name") or narrative.identity.name)
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
                    start_at=str(period.get("start_at")) if period.get("start_at") else None,
                    end_at=str(period.get("end_at")) if period.get("end_at") else None,
                    highlights=[str(x) for x in period.get("highlights", [])]
                    if isinstance(period.get("highlights"), list)
                    else [],
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

    save(narrative, path)
    return narrative


def summarize_short(narrative: SelfNarrative | None = None, path: Path | str | None = None) -> str:
    """Return a compact one-line summary."""

    current = narrative or load(path)
    return (
        f"{current.identity.name} · âge logique {current.identity.logical_age}j · "
        f"cap: {current.current_heading}"
    )


def summarize_long(narrative: SelfNarrative | None = None, path: Path | str | None = None) -> str:
    """Return a richer human-readable summary."""

    current = narrative or load(path)
    traits = ", ".join(
        f"{name}={trend.value:.2f} ({trend.trend})"
        for name, trend in current.trait_trends.items()
    )
    periods = "; ".join(period.title for period in current.life_periods[-3:]) or "aucune période marquante"

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
