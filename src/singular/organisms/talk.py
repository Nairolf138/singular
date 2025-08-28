"""Talk command implementation."""

from __future__ import annotations

import os
from typing import Callable

from ..memory import add_episode, ensure_memory_structure, read_episodes
from ..psyche import Psyche
from ..providers import load_llm_provider


def _default_reply(prompt: str) -> str:
    """Fallback reply generation when no provider is available."""

    return f"I heard you say: {prompt}"


def talk(provider: str | None = None, seed: int | None = None) -> None:
    """Handle the ``talk`` subcommand.

    Parameters
    ----------
    provider:
        Optional name of the LLM provider. Overrides environment variables.
    seed:
        Optional random seed for reproducibility.
    """

    ensure_memory_structure()

    provider_name = provider or os.getenv("LLM_PROVIDER")
    if not provider_name:
        provider_name = "openai" if os.getenv("OPENAI_API_KEY") else "stub"
    generate_reply: Callable[[str], str] | None = load_llm_provider(provider_name)
    if generate_reply is None:
        generate_reply = _default_reply

    psyche = Psyche()

    while True:
        episodes = read_episodes()
        last_event = episodes[-1]["text"] if episodes else None

        try:
            user_input = input("you: ")
        except EOFError:
            break

        if user_input.strip().lower() in {"exit", "quit"}:
            break

        add_episode({"role": "user", "text": user_input})

        mood = psyche.feel("neutral")
        reply = generate_reply(user_input)

        parts = [reply]
        if last_event:
            parts.append(f"Reminder: {last_event}")
        parts.append(f"Mood: {psyche.last_mood}")
        response = " | ".join(parts)

        print(response)
        add_episode({"role": "assistant", "text": response, "mood": mood})
