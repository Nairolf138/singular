"""Talk command implementation."""

from __future__ import annotations

import os
import random
from typing import Callable

from ..memory import add_episode, ensure_memory_structure, read_episodes
from ..psyche import Psyche
from ..providers import load_llm_provider


def _default_reply(prompt: str, rng: random.Random) -> str:
    """Fallback reply generation when no provider is available.

    The ``seed`` passed to :func:`talk` is used to seed ``rng`` so that stub
    responses become deterministic when desired.
    """

    options = [
        "I heard you say",
        "You said",
        "Echoing",
    ]
    return f"{rng.choice(options)}: {prompt}"


def talk(provider: str | None = None, seed: int | None = None) -> None:
    """Handle the ``talk`` subcommand.

    Parameters
    ----------
    provider:
        Optional name of the LLM provider. Overrides environment variables.
    seed:
        Optional random seed for reproducibility. It affects stub replies when
        no provider is available.
    """

    ensure_memory_structure()

    rng = random.Random(seed)

    provider_name = provider or os.getenv("LLM_PROVIDER")
    if not provider_name:
        provider_name = "openai" if os.getenv("OPENAI_API_KEY") else "stub"
    generate_reply: Callable[[str], str] | None = load_llm_provider(provider_name)
    if generate_reply is None:
        generate_reply = lambda prompt: _default_reply(prompt, rng)

    psyche = Psyche.load_state()

    while True:
        episodes = read_episodes()
        last_event = next((e["text"] for e in reversed(episodes) if "text" in e), None)
        latest_mutation = next(
            (e for e in reversed(episodes) if e.get("event") == "mutation"),
            None,
        )
        last_success = next(
            (
                e
                for e in reversed(episodes)
                if e.get("event") == "mutation" and e.get("improved")
            ),
            None,
        )
        last_failure = next(
            (
                e
                for e in reversed(episodes)
                if e.get("event") == "mutation" and not e.get("improved")
            ),
            None,
        )
        mood_event = latest_mutation.get("mood") if latest_mutation else None
        perf_msg = None
        if latest_mutation:
            if latest_mutation.get("improved"):
                sb = latest_mutation.get("score_base")
                sn = latest_mutation.get("score_new")
                if isinstance(sb, (int, float)) and isinstance(sn, (int, float)):
                    perf_msg = f"score improved from {sb:.2f} to {sn:.2f}"
            else:
                msb = latest_mutation.get("ms_base")
                msn = latest_mutation.get("ms_new")
                if isinstance(msb, (int, float)) and isinstance(msn, (int, float)):
                    diff = msn - msb
                    if diff > 0:
                        perf_msg = f"runtime increased by {diff:.2f}ms"
                    elif diff < 0:
                        perf_msg = f"runtime decreased by {abs(diff):.2f}ms"
        mood_report = mood_event or psyche.last_mood or "neutral"

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
        if last_success:
            parts.append(f"Last success: {last_success.get('op')}")
        if last_failure:
            parts.append(f"Last failure: {last_failure.get('op')}")
        if perf_msg:
            parts.append(perf_msg)
        parts.append(f"Mood: {mood_report}")
        response = " | ".join(parts)

        print(response)
        add_episode({"role": "assistant", "text": response, "mood": mood})
        psyche.save_state()
