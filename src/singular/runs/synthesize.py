"""Synthesize command implementation."""

from __future__ import annotations

from ..memory import add_episode, ensure_memory_structure


def synthesize(code: str) -> None:
    """Persist the winning *code* snippet into episodic memory.

    Parameters
    ----------
    code:
        Code to store. It is appended as a "system" episode so that the talk
        loop can recall it as a reminder.
    """

    ensure_memory_structure()
    add_episode({"role": "system", "text": code})
