"""Birth command implementation."""

from __future__ import annotations

from ..memory import ensure_memory_structure


def birth(seed: int | None = None) -> None:
    """Handle the ``birth`` subcommand.

    Parameters
    ----------
    seed:
        Optional random seed for reproducibility.
    """
    ensure_memory_structure()
