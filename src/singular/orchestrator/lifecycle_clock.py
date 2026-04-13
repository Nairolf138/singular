"""Lifecycle clock configuration helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[3] / "configs" / "lifecycle.yaml"


@dataclass(frozen=True)
class CycleParameters:
    """Durations and frequencies driving the lifecycle clock."""

    veille_seconds: float = 2.0
    sommeil_seconds: float = 3.0
    introspection_frequency_ticks: int = 1
    mutation_window_seconds: float = 0.2


@dataclass(frozen=True)
class PhaseBehavior:
    """Operational budget and behavior flags for one phase."""

    cpu_budget_percent: float
    slowdown_on_fatigue: float
    allowed_actions: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class LifecycleClockConfig:
    """Complete lifecycle clock config with sane defaults."""

    cycle: CycleParameters = field(default_factory=CycleParameters)
    phases: dict[str, PhaseBehavior] = field(
        default_factory=lambda: {
            "veille": PhaseBehavior(30.0, 1.1, ("perception", "resource_scan")),
            "action": PhaseBehavior(75.0, 1.5, ("mutation", "evaluation", "checkpoint")),
            "introspection": PhaseBehavior(40.0, 1.2, ("self_review", "memory_consolidation")),
            "sommeil": PhaseBehavior(15.0, 1.0, ("recovery", "cooldown")),
        }
    )


def _parse_scalar(value: str) -> Any:
    text = value.strip()
    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        if not inner:
            return []
        return [chunk.strip().strip('"').strip("'") for chunk in inner.split(",")]
    try:
        return int(text)
    except ValueError:
        try:
            return float(text)
        except ValueError:
            return text.strip('"').strip("'")


def _load_simple_yaml(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(0, data)]

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        key, value = line.strip().split(":", 1)
        while stack and indent < stack[-1][0]:
            stack.pop()
        current = stack[-1][1]
        if not value.strip():
            new: dict[str, Any] = {}
            current[key.strip()] = new
            stack.append((indent + 2, new))
            continue
        current[key.strip()] = _parse_scalar(value)
    return data


def load_lifecycle_clock_config(path: Path | None = None) -> LifecycleClockConfig:
    """Load lifecycle clock config and merge with defaults."""

    selected = path or DEFAULT_CONFIG_PATH
    cfg = LifecycleClockConfig()
    if not selected.exists():
        return cfg

    raw = _load_simple_yaml(selected)
    cycle_raw = raw.get("cycle", {})
    phases_raw = raw.get("phases", {})

    cycle = CycleParameters(
        veille_seconds=float(cycle_raw.get("veille_seconds", cfg.cycle.veille_seconds)),
        sommeil_seconds=float(cycle_raw.get("sommeil_seconds", cfg.cycle.sommeil_seconds)),
        introspection_frequency_ticks=int(
            cycle_raw.get(
                "introspection_frequency_ticks",
                cfg.cycle.introspection_frequency_ticks,
            )
        ),
        mutation_window_seconds=float(
            cycle_raw.get("mutation_window_seconds", cfg.cycle.mutation_window_seconds)
        ),
    )

    phases: dict[str, PhaseBehavior] = {}
    for name, default in cfg.phases.items():
        source = phases_raw.get(name, {}) if isinstance(phases_raw, dict) else {}
        actions = source.get("allowed_actions", list(default.allowed_actions))
        if isinstance(actions, str):
            actions = [actions]
        phases[name] = PhaseBehavior(
            cpu_budget_percent=float(source.get("cpu_budget_percent", default.cpu_budget_percent)),
            slowdown_on_fatigue=float(source.get("slowdown_on_fatigue", default.slowdown_on_fatigue)),
            allowed_actions=tuple(str(item) for item in actions),
        )

    if cycle.introspection_frequency_ticks <= 0:
        raise ValueError("introspection_frequency_ticks must be > 0")
    if cycle.mutation_window_seconds <= 0:
        raise ValueError("mutation_window_seconds must be > 0")

    return LifecycleClockConfig(cycle=cycle, phases=phases)
