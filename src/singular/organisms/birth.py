"""Birth command implementation."""

from __future__ import annotations

import os
import random
import string
from pathlib import Path

from ..identity import create_identity
from ..memory import ensure_memory_structure, update_score, write_profile
from ..psyche import Psyche


def birth(seed: int | None = None, home: Path | None = None) -> None:
    """Handle the ``birth`` subcommand.

    Parameters
    ----------
    seed:
        Optional random seed for reproducibility.
    """
    if home is None:
        if "SINGULAR_HOME" in os.environ:
            home = Path(os.environ["SINGULAR_HOME"])
        else:
            home = Path.cwd()
    else:
        home = Path(home)

    home.mkdir(parents=True, exist_ok=True)
    ensure_memory_structure(home / "mem")

    skills_dir = home / "skills"
    if not skills_dir.exists() or not any(skills_dir.iterdir()):
        skills_dir.mkdir(parents=True, exist_ok=True)
        default_skills = {
            "addition.py": (
                '"""Simple addition skill."""\n\n'
                "def add(a: float, b: float) -> float:\n"
                '    """Return the sum of ``a`` and ``b``."""\n'
                "    return a + b\n"
            ),
            "subtraction.py": (
                '"""Simple subtraction skill."""\n\n'
                "def subtract(a: float, b: float) -> float:\n"
                '    """Return the difference of ``a`` and ``b``."""\n'
                "    return a - b\n"
            ),
            "multiplication.py": (
                '"""Simple multiplication skill."""\n\n'
                "def multiply(a: float, b: float) -> float:\n"
                '    """Return the product of ``a`` and ``b``."""\n'
                "    return a * b\n"
            ),
        }
        for filename, code in default_skills.items():
            (skills_dir / filename).write_text(code, encoding="utf-8")
            update_score(
                filename.removesuffix(".py"),
                0.0,
                path=home / "mem" / "skills.json",
            )

    if seed is not None:
        random.seed(seed)

    # Generate a random name and soulseed for the new identity
    name = f"organism-{random.randint(0, 999999):06d}"
    soulseed = "".join(random.choices(string.ascii_lowercase + string.digits, k=16))

    # Create the identity file and persist a base profile
    identity = create_identity(name, soulseed, path=home / "id.json")
    write_profile(identity.__dict__, path=home / "mem" / "profile.json")

    # Initialize the psyche with default traits and save its state
    psyche = Psyche()
    psyche.save_state(path=home / "mem" / "psyche.json")
