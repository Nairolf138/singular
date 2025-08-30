from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import List

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
            for field in ("energy", "food", "warmth"):
                if field in data:
                    setattr(self, field, float(data[field]))

    # internal helpers -----------------------------------------------------
    def _clamp(self) -> None:
        self.energy = max(0.0, min(100.0, self.energy))
        self.food = max(0.0, min(100.0, self.food))
        self.warmth = max(0.0, min(100.0, self.warmth))

    def _save(self) -> None:
        data = {"energy": self.energy, "food": self.food, "warmth": self.warmth}
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
        self.food += amount
        self._clamp()
        self._save()

    def metabolize(self, rate: float = 0.1) -> None:
        """Convert stored food into energy.

        ``rate`` units of food are consumed and twice that amount of energy is
        regenerated. Values are clamped to the ``[0, 100]`` range and the state
        is persisted.
        """

        self.food -= rate
        self.energy += rate * 2
        self._clamp()
        self._save()

    def cool_down(self, amount: float) -> None:
        self.warmth -= amount
        self._clamp()
        self._save()

    def add_warmth(self, amount: float) -> None:
        self.warmth += amount
        self._clamp()
        self._save()

    def update_from_environment(self, temp: float) -> None:
        """Adjust ``warmth`` based on the surrounding temperature.

        ``20°C`` is treated as neutral. Temperatures above this increase
        warmth while colder values decrease it.
        """

        neutral = 20.0
        diff = temp - neutral
        if diff > 0:
            self.add_warmth(diff * 0.1)
        elif diff < 0:
            self.cool_down(-diff * 0.1)

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
