"""Synthesize command implementation."""

from __future__ import annotations

from ..memory import add_episode, ensure_memory_structure


def synthesize(code: str, seed: int | None = None) -> None:
    """Persist the winning *code* snippet into episodic memory.

    Parameters
    ----------
    code:
        Code to store. It is appended as a "system" episode so that the talk
        loop can recall it as a reminder.
    seed:
        Optional random seed for reproducibility. (Currently unused.)
    """

    ensure_memory_structure()
    add_episode({"role": "system", "text": code})
