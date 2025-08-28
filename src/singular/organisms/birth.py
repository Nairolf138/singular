"""Birth command implementation."""

from __future__ import annotations

import random
import string

from ..identity import create_identity
from ..memory import ensure_memory_structure, write_profile
from ..psyche import Psyche


def birth(seed: int | None = None) -> None:
    """Handle the ``birth`` subcommand.

    Parameters
    ----------
    seed:
        Optional random seed for reproducibility.
    """
    ensure_memory_structure()

    if seed is not None:
        random.seed(seed)

    # Generate a random name and soulseed for the new identity
    name = f"organism-{random.randint(0, 999999):06d}"
    soulseed = "".join(
        random.choices(string.ascii_lowercase + string.digits, k=16)
    )

    # Create the identity file and persist a base profile
    identity = create_identity(name, soulseed)
    write_profile(identity.__dict__)

    # Initialize the psyche with default traits and save its state
    psyche = Psyche()
    psyche.save_state()
