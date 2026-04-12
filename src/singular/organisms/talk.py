"""Talk command implementation."""

from __future__ import annotations

import os
import random
import time

from ..memory import add_episode, ensure_memory_structure, read_episodes
from ..perception import capture_signals
from ..psyche import Mood, Psyche
from ..providers import (
    LLMProviderError,
    ProviderMisconfiguredError,
    ProviderQuotaExceededError,
    ProviderRetryExhaustedError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    load_llm_client,
)
from ..runs.logger import log_provider_event


def _default_reply(prompt: str, rng: random.Random) -> str:
    """Fallback reply generation when no provider is available."""

    options = [
        "I heard you say",
        "You said",
        "Echoing",
    ]
    return f"{rng.choice(options)}: {prompt}"


def _user_message_for_error(provider: str, err: LLMProviderError) -> str:
    if isinstance(err, ProviderMisconfiguredError):
        return (
            f"Provider '{provider}' is misconfigured (missing or invalid credentials). "
            "Using local fallback replies."
        )
    if isinstance(err, ProviderQuotaExceededError):
        return (
            f"Provider '{provider}' quota is exceeded (or rate-limited). "
            "Using local fallback replies."
        )
    if isinstance(err, ProviderTimeoutError):
        return f"Provider '{provider}' timed out. Using local fallback replies."
    if isinstance(err, ProviderUnavailableError):
        return f"Provider '{provider}' is unavailable. Using local fallback replies."
    if isinstance(err, ProviderRetryExhaustedError):
        return f"Provider '{provider}' retries exhausted. Using local fallback replies."
    return f"Provider '{provider}' failed unexpectedly. Using local fallback replies."


def talk(
    provider: str | None = None,
    seed: int | None = None,
    prompt: str | None = None,
) -> None:
    """Handle the ``talk`` subcommand."""

    ensure_memory_structure()

    rng = random.Random(seed)

    provider_name = provider or os.getenv("LLM_PROVIDER")
    if not provider_name:
        provider_name = "openai" if os.getenv("OPENAI_API_KEY") else "stub"
    print(f"Provider: {provider_name}")

    client = load_llm_client(provider_name)
    if client is None:
        print(
            f"Provider '{provider_name}' not found. "
            "Using local fallback replies."
        )

    psyche = Psyche.load_state()

    def gather_context() -> (
        tuple[str | None, dict | None, dict | None, str | None, str | None]
    ):
        signals = capture_signals()
        add_episode({"event": "perception", **signals})
        psyche.consume()
        episodes = read_episodes()
        episodes_by_role = {
            "user": [e for e in episodes if e.get("role") == "user"],
            "assistant": [e for e in episodes if e.get("role") == "assistant"],
        }
        user_episodes = episodes_by_role["user"]
        last_event = next(
            (e.get("text") for e in reversed(user_episodes) if e.get("text")),
            None,
        )
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
        return last_event, last_success, last_failure, mood_event, perf_msg

    def respond(
        user_input: str,
        last_event: str | None,
        last_success: dict | None,
        last_failure: dict | None,
        mood_event: str | None,
        perf_msg: str | None,
    ) -> None:
        add_episode({"role": "user", "text": user_input})
        mood = psyche.feel(Mood.NEUTRAL)
        mood_report = mood_event or mood.value

        start = time.perf_counter()
        fallback_used = client is None
        error_category: str | None = "provider_missing" if client is None else None

        if client is None:
            reply = _default_reply(user_input, rng)
        else:
            try:
                reply = client.generate_reply(user_input)
            except LLMProviderError as err:
                fallback_used = True
                error_category = getattr(err, "category", "provider_error")
                print(_user_message_for_error(provider_name, err))
                reply = _default_reply(user_input, rng)

        latency_ms = (time.perf_counter() - start) * 1000
        log_provider_event(
            provider=provider_name,
            latency_ms=latency_ms,
            fallback=fallback_used,
            error_category=error_category,
        )

        parts = [reply]
        should_add_reminder = bool(last_event) and (
            "Reminder:" not in reply and last_event not in reply
        )
        if should_add_reminder:
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
        add_episode(
            {
                "role": "assistant",
                "text": response,
                "raw_reply": reply,
                "mood": mood.value,
            }
        )
        psyche.gain()
        psyche.save_state()

    if prompt is not None:
        context = gather_context()
        respond(prompt, *context)
        return

    while True:
        context = gather_context()
        try:
            user_input = input("you: ")
        except EOFError:
            break
        except KeyboardInterrupt:
            print("\nExiting conversation.")
            break

        if user_input.strip().lower() in {"exit", "quit"}:
            break

        respond(user_input, *context)
