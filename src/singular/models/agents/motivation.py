from __future__ import annotations

"""Motivation data structure for agent needs."""

from dataclasses import dataclass, field
from typing import Dict


@dataclass
class Motivation:
    """Store motivation values for various needs.

    Each key of :attr:`needs` represents a need (e.g. ``"hunger"``) and the
    associated value is its priority. Higher values indicate stronger
    motivation to satisfy the need.
    """

    needs: Dict[str, float] = field(default_factory=dict)
