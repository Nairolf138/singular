"""Quest command implementation."""

from __future__ import annotations

from pathlib import Path

from life.synthesis import synthesise

from ..memory import add_episode, ensure_memory_structure, update_score
from ..psyche import Psyche


def quest(spec: Path) -> None:
    """Handle the ``quest`` subcommand.

    Parameters
    ----------
    spec:
        Path to the JSON specification describing the desired skill.
    """

    ensure_memory_structure()
    psyche = Psyche.load_state()

    try:
        skill_path = synthesise(spec, Path("skills"))
    except Exception as exc:  # pragma: no cover - re-raised after logging
        mood = psyche.feel("frustrated")
        add_episode(
            {"event": "quest", "status": "failure", "error": str(exc), "mood": mood}
        )
        psyche.save_state()
        raise

    update_score(skill_path.stem, 0.0)
    mood = psyche.feel("proud")
    add_episode(
        {"event": "quest", "status": "success", "skill": skill_path.stem, "mood": mood}
    )
    psyche.gain()
    psyche.save_state()
