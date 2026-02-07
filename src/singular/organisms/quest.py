"""Quest command implementation."""

from __future__ import annotations

import os
from pathlib import Path

from singular.life.synthesis import synthesise

from ..memory import add_episode, ensure_memory_structure, update_score
from ..psyche import Psyche, Mood


def quest(spec: Path) -> None:
    """Handle the ``quest`` subcommand.

    Parameters
    ----------
    spec:
        Path to the JSON specification describing the desired skill.
    """

    ensure_memory_structure()
    psyche = Psyche.load_state()

    base_dir = Path(os.environ.get("SINGULAR_HOME", Path.cwd()))
    skills_root = base_dir / "skills"
    skills_root.mkdir(parents=True, exist_ok=True)

    try:
        skill_path = synthesise(spec, skills_root)
    except Exception as exc:  # pragma: no cover - re-raised after logging
        mood = psyche.feel(Mood.FRUSTRATED)
        add_episode(
            {
                "event": "quest",
                "status": "failure",
                "error": str(exc),
                "mood": mood.value,
            }
        )
        psyche.save_state()
        raise

    update_score(skill_path.stem, 0.0)
    mood = psyche.feel(Mood.PROUD)
    add_episode(
        {
            "event": "quest",
            "status": "success",
            "skill": skill_path.stem,
            "mood": mood.value,
        }
    )
    psyche.gain()
    psyche.save_state()
