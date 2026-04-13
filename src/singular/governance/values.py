"""Loader and validator for value weights used in critical decisions."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

from singular.memory import get_values_file, read_values


VALUE_KEYS = (
    "securite",
    "utilite_utilisateur",
    "preservation_memoire",
    "curiosite_bornee",
)


class ValuesSchemaError(ValueError):
    """Raised when ``values.yaml`` does not follow the expected schema."""


@dataclass(frozen=True)
class ValueWeights:
    """Normalized weights used by governance and objective prioritization."""

    securite: float = 0.35
    utilite_utilisateur: float = 0.25
    preservation_memoire: float = 0.25
    curiosite_bornee: float = 0.15

    def normalized(self) -> "ValueWeights":
        raw = {name: max(0.0, float(value)) for name, value in asdict(self).items()}
        total = sum(raw.values())
        if total <= 0.0:
            return ValueWeights()
        return ValueWeights(**{name: value / total for name, value in raw.items()})

    def to_dict(self) -> dict[str, float]:
        return asdict(self.normalized())


def _coerce_float(payload: Mapping[str, Any], key: str) -> float:
    if key not in payload:
        raise ValuesSchemaError(f"missing required key: {key}")
    value = payload[key]
    try:
        cast = float(value)
    except (TypeError, ValueError) as exc:
        raise ValuesSchemaError(f"invalid numeric value for {key}: {value!r}") from exc
    if cast < 0.0:
        raise ValuesSchemaError(f"value for {key} must be >= 0")
    return cast


def validate_values_payload(payload: Mapping[str, Any]) -> ValueWeights:
    """Validate payload schema and return normalized value weights."""

    if not isinstance(payload, Mapping):
        raise ValuesSchemaError("values payload must be a mapping")

    candidate = payload.get("values", payload)
    if not isinstance(candidate, Mapping):
        raise ValuesSchemaError("`values` section must be a mapping")

    unexpected = sorted(set(candidate.keys()) - set(VALUE_KEYS))
    if unexpected:
        raise ValuesSchemaError(f"unexpected keys: {', '.join(unexpected)}")

    weights = ValueWeights(
        securite=_coerce_float(candidate, "securite"),
        utilite_utilisateur=_coerce_float(candidate, "utilite_utilisateur"),
        preservation_memoire=_coerce_float(candidate, "preservation_memoire"),
        curiosite_bornee=_coerce_float(candidate, "curiosite_bornee"),
    ).normalized()
    return weights


def load_value_weights(path: Path | None = None) -> ValueWeights:
    """Load and validate ``values.yaml``. Falls back to defaults if absent."""

    values_path = Path(path) if path is not None else get_values_file()
    if not values_path.exists() or values_path.stat().st_size == 0:
        return ValueWeights()

    payload = read_values(values_path)
    if not payload:
        return ValueWeights()
    return validate_values_payload(payload)


__all__ = [
    "VALUE_KEYS",
    "ValueWeights",
    "ValuesSchemaError",
    "load_value_weights",
    "validate_values_payload",
]
