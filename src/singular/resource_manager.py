from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List
from uuid import uuid4

from .memory import add_causal_trace
from .memory import _atomic_write_text


@dataclass
class ResourceManager:
    """Track and mutate basic survival resources.

    The state is optionally persisted to ``path`` so separate processes can
    communicate through a simple file based protocol.  Energy, food and warmth
    values are kept in the ``[0, 100]`` range.
    """

    energy: float = 100.0
    food: float = 50.0
    warmth: float = 50.0
    ecological_debt: float = 0.0
    relational_debt: float = 0.0
    path: Path = Path("resources.json")
    energy_threshold: float = 20.0
    food_threshold: float = 20.0
    warmth_threshold: float = 20.0

    def __post_init__(self) -> None:
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                return
            for field in ("energy", "food", "warmth", "ecological_debt", "relational_debt"):
                if field in data:
                    setattr(self, field, float(data[field]))

    # internal helpers -----------------------------------------------------
    def _clamp(self) -> None:
        self.energy = max(0.0, min(100.0, self.energy))
        self.food = max(0.0, min(100.0, self.food))
        self.warmth = max(0.0, min(100.0, self.warmth))
        self.ecological_debt = max(0.0, min(100.0, self.ecological_debt))
        self.relational_debt = max(0.0, min(100.0, self.relational_debt))

    def _save(self) -> None:
        data = {
            "energy": self.energy,
            "food": self.food,
            "warmth": self.warmth,
            "ecological_debt": self.ecological_debt,
            "relational_debt": self.relational_debt,
        }
        _atomic_write_text(self.path, json.dumps(data))

    # mutation methods -----------------------------------------------------
    def consume_energy(self, amount: float) -> None:
        self.energy -= amount
        self._clamp()
        self._save()

    def regenerate_energy(self, amount: float) -> None:
        self.energy += amount
        self._clamp()
        self._save()

    def consume_food(self, amount: float) -> None:
        self.food -= amount
        self._clamp()
        self._save()

    def add_food(self, amount: float) -> None:
        effective = amount * max(0.2, 1.0 - (self.ecological_debt / 150.0))
        self.food += effective
        self._clamp()
        self._save()

    def metabolize(self, rate: float = 0.1) -> None:
        """Convert stored food into energy.

        ``rate`` units of food are consumed and twice that amount of energy is
        regenerated. Values are clamped to the ``[0, 100]`` range and the state
        is persisted.
        """

        eco_penalty = self.ecological_debt / 100.0
        self.food -= rate * (1.0 + (0.35 * eco_penalty))
        self.energy += (rate * 2) * max(0.2, 1.0 - (0.5 * eco_penalty))
        self._clamp()
        self._save()

    def cool_down(self, amount: float) -> None:
        self.warmth -= amount
        self._clamp()
        self._save()

    def add_warmth(self, amount: float) -> None:
        effective = amount * max(0.25, 1.0 - (self.relational_debt / 140.0))
        self.warmth += effective
        self._clamp()
        self._save()

    def apply_world_state(self, world_state: dict[str, object] | None) -> None:
        """Project world debts into local resources to model indirect mortality pressure."""

        if not isinstance(world_state, dict):
            return
        dynamics = world_state.get("dynamics")
        signals = (
            world_state.get("global_health", {}).get("signals", {})
            if isinstance(world_state.get("global_health"), dict)
            else {}
        )
        eco_norm = 0.0
        rel_norm = 0.0
        delayed_risk = 0.0
        if isinstance(dynamics, dict):
            eco_norm = max(0.0, min(1.0, float(dynamics.get("ecological_debt", 0.0)) / 100.0))
            rel_norm = max(0.0, min(1.0, float(dynamics.get("relational_debt", 0.0)) / 100.0))
        if isinstance(signals, dict):
            delayed_risk = max(0.0, min(1.0, float(signals.get("delayed_risk", 0.0))))

        self.ecological_debt = (self.ecological_debt * 0.7) + (eco_norm * 100.0 * 0.3)
        self.relational_debt = (self.relational_debt * 0.7) + (rel_norm * 100.0 * 0.3)

        stress_factor = (eco_norm * 0.6) + (rel_norm * 0.4) + (delayed_risk * 0.5)
        self.energy -= stress_factor * 1.8
        self.food -= (eco_norm + delayed_risk) * 0.9
        self.warmth -= (rel_norm * 1.0) + (delayed_risk * 0.4)
        self._clamp()
        self._save()

    def update_from_environment(self, temp: float) -> None:
        """Adjust ``warmth`` based on the surrounding temperature.

        ``20°C`` is treated as neutral. Temperatures above this increase
        warmth while colder values decrease it.
        """

        neutral = 20.0
        before = self.warmth
        diff = temp - neutral
        decision = "hold"
        if diff > 0:
            decision = "warm_up"
            self.add_warmth(diff * 0.1)
        elif diff < 0:
            decision = "cool_down"
            self.cool_down(-diff * 0.1)
        after = self.warmth
        delta = round(after - before, 3)
        add_causal_trace(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "trace_id": uuid4().hex,
                "pipeline": "environment.resource_manager",
                "input": {"kind": "world_event", "temperature_c": temp},
                "decision": {"temperature_delta_from_neutral": round(diff, 3), "selected": decision},
                "action": {"kind": decision, "warmth_before": round(before, 3), "warmth_after": round(after, 3)},
                "result": {
                    "gain_loss": delta,
                    "objective_impact": {"objective": "homeostasis.warmth", "impact": delta},
                },
            }
        )

    def simulate_human_interaction(self, amount: float = 5.0) -> None:
        """API used by tests/CLI to increase warmth."""
        self.add_warmth(amount)

    # mood -----------------------------------------------------------------
    def mood(self) -> List[str]:
        """Return a list describing the mood derived from resources."""
        moods: List[str] = []
        if self.energy < self.energy_threshold:
            moods.append("tired")
        if self.food < self.food_threshold:
            moods.append("angry")
        if self.warmth < self.warmth_threshold:
            moods.append("cold")
        if self.relational_debt >= 55.0:
            moods.append("tense")
        if self.ecological_debt >= 60.0:
            moods.append("strained")
        if not moods:
            moods.append("content")
        return moods


# ---------------------------------------------------------------------------
# CLI helpers


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="resource manager")
    sub = parser.add_subparsers(dest="cmd")
    warm = sub.add_parser("warm", help="increase warmth via human interaction")
    warm.add_argument("--amount", type=float, default=5.0)
    return parser


def main(argv: list[str] | None = None) -> None:  # pragma: no cover - CLI wrapper
    args = _build_parser().parse_args(argv)
    rm = ResourceManager()
    if args.cmd == "warm":
        rm.simulate_human_interaction(args.amount)
        print(f"warmth={rm.warmth}")


if __name__ == "__main__":  # pragma: no cover - module executable
    main()
