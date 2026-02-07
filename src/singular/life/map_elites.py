from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, Tuple
import random

Descriptor = Tuple[int, int]
DescriptorFunc = Callable[[str, float], Tuple[int, int]]


@dataclass
class MapElites:
    """Simple MAP-Elites grid.

    The grid is indexed by discrete descriptor values returned by a
    ``descriptor_func`` which maps a code string and its score to a pair
    of integers.  Each cell stores the best code (lowest score) observed
    for that descriptor.
    """

    descriptor_func: DescriptorFunc
    bins: Descriptor = (10, 10)
    grid: Dict[Descriptor, Tuple[str, float]] = field(default_factory=dict)

    def _bin(self, desc: Tuple[int, int]) -> Descriptor:
        x, y = desc
        bx = max(0, min(self.bins[0] - 1, int(x)))
        by = max(0, min(self.bins[1] - 1, int(y)))
        return bx, by

    def add(self, code: str, score: float) -> bool:
        """Insert ``code`` into the grid if it improves its cell.

        Returns ``True`` if the code was stored, ``False`` otherwise.
        """

        cell = self._bin(self.descriptor_func(code, score))
        current = self.grid.get(cell)
        if current is None or score <= current[1]:
            self.grid[cell] = (code, score)
            return True
        return False

    def sample(self, rng: random.Random) -> str:
        """Return a random elite code from the grid."""

        if not self.grid:
            raise RuntimeError("empty grid")
        return rng.choice(list(self.grid.values()))[0]

    def regions(self) -> Dict[Descriptor, str]:
        """Return a mapping of filled cells to their stored code."""

        return {cell: data[0] for cell, data in self.grid.items()}
