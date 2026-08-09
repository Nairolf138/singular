"""Talk command implementation."""

from __future__ import annotations

import os
import random
import time
import re
from typing import Mapping, Any
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4

from ..memory import (
    add_causal_trace,
    add_episode,
    ensure_memory_structure,
    format_recalled_memories,
    read_episodes,
)
from ..memory_layers import MemoryRetrievalService, build_backend
from ..perception import capture_signals
from ..psyche import Mood, Psyche
from ..self_narrative import load as load_self_narrative, summarize_short
from ..providers import (
    FallbackLLMClient,
    LLMProviderError,
    ProviderMisconfiguredError,
    ProviderQuotaExceededError,
    ProviderRetryExhaustedError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    PROVIDER_CONFIGURATION_COMMANDS,
    describe_client,
    load_llm_client,
    provider_is_real,
)
from ..runs.logger import log_provider_event
from ..learning.imitation import ImitationEngine

_CONTEXT_BUDGET_CHARS = 420
_UNKNOWN_GUARD = 'Garde anti-hallucination: si une information demandée est inconnue, réponds explicitement "inconnu".'


def _default_reply(prompt: str, rng: random.Random) -> str:
    """Fallback reply generation when no provider is available."""

    options = [
        "I heard you say",
        "You said",
        "Echoing",
    ]
    return f"[RÉPONSE DÉTERMINISTE/FACTICE — aucun LLM réel] {rng.choice(options)}: {prompt}"


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


def _extract_structured_signals(text: str) -> dict[str, object]:
    lowered = text.lower()
    frustration_tokens = {
        "bug",
        "erreur",
        "error",
        "frustr",
        "bloqué",
        "bloque",
        "impossible",
        "nul",
        "fail",
        "failed",
        "wtf",
    }
    satisfaction_tokens = {
        "merci",
        "super",
        "parfait",
        "great",
        "thanks",
        "top",
        "cool",
        "good",
        "bien",
    }
    urgency_tokens = {
        "urgent",
        "asap",
        "vite",
        "maintenant",
        "now",
        "immédiat",
        "immediat",
        "deadline",
    }
    token_count = max(1, len(re.findall(r"\w+", lowered)))
    frustration = min(
        1.0,
        sum(1 for token in frustration_tokens if token in lowered)
        / max(1.0, token_count * 0.2),
    )
    satisfaction = min(
        1.0,
        sum(1 for token in satisfaction_tokens if token in lowered)
        / max(1.0, token_count * 0.2),
    )
    urgency = min(
        1.0,
        0.35 * float("!" in text or "?" in text)
        + sum(1 for token in urgency_tokens if token in lowered) * 0.35,
    )
    theme = "general"
    for candidate, keywords in (
        ("bugfix", ("bug", "erreur", "fix", "incident")),
        ("performance", ("lent", "slow", "optim", "performance", "latence")),
        ("planning", ("roadmap", "plan", "deadline", "priorit")),
        ("support", ("help", "aide", "explain", "comprendre")),
    ):
        if any(keyword in lowered for keyword in keywords):
            theme = candidate
            break
    return {
        "frustration": round(frustration, 3),
        "satisfaction": round(satisfaction, 3),
        "urgency": round(urgency, 3),
        "theme": theme,
    }


def _trim_for_budget(text: str, budget: int) -> str:
    cleaned = " ".join(text.split())
    if budget <= 3:
        return cleaned[:budget]
    if len(cleaned) <= budget:
        return cleaned
    return f"{cleaned[: budget - 3]}..."


def _build_system_preamble(
    *,
    narrative_summary: str,
    last_event: str | None,
    mood_event: str | None,
    recalled_memory_summary: str | None = None,
) -> str:
    available_for_summary = max(0, _CONTEXT_BUDGET_CHARS - len(_UNKNOWN_GUARD) - 120)
    summary = _trim_for_budget(narrative_summary, available_for_summary)
    event_fragment = _trim_for_budget(last_event or "inconnu", 80)
    mood_fragment = _trim_for_budget(mood_event or "inconnu", 40)
    preamble = (
        f"Contexte identitaire: {summary}\n"
        f"Dernier événement utilisateur: {event_fragment}\n"
        f"Humeur récente: {mood_fragment}\n"
        f"Souvenirs pertinents: {_trim_for_budget(recalled_memory_summary or 'aucun souvenir pertinent', 120)}\n"
        f"{_UNKNOWN_GUARD}"
    )
    return _trim_for_budget(preamble, _CONTEXT_BUDGET_CHARS)


def talk(
    provider: str | None = None,
    seed: int | None = None,
    prompt: str | None = None,
    demonstration: Mapping[str, Any] | None = None,
    imitation_engine: ImitationEngine | None = None,
    life_home: Path | str | None = None,
) -> str | None:
    """Handle the ``talk`` subcommand."""

    life_root = (
        Path(life_home)
        if life_home is not None
        else Path(os.environ.get("SINGULAR_HOME", "."))
    )
    mem_dir = life_root / "mem"
    episodic_file = mem_dir / "episodic.jsonl"
    causal_file = mem_dir / "causal_timeline.jsonl"
    psyche_file = mem_dir / "psyche.json"
    narrative_file = mem_dir / "self_narrative.json"
    ensure_memory_structure(mem_dir)

    # Human dialogue is eligible for teaching only through a separate,
    # structured and explicitly consented demonstration payload.
    if demonstration is not None:
        (imitation_engine or ImitationEngine(life_root)).ingest_interaction(
            demonstration, source="human:talk"
        )

    rng = random.Random(seed)

    # Keep the user's selection separate from the backend (or fallback chain)
    # resolved by the provider loader.  None deliberately enables its automatic
    # fallback policy; credentials must not silently turn into a selection here.
    requested_provider = provider or os.getenv("LLM_PROVIDER") or None
    provider_selection = requested_provider or "automatic"
    print(f"Provider: {provider_selection}")

    client = load_llm_client(requested_provider)
    provider_status = describe_client(client, requested_provider)
    if client is None:
        print(
            "Provider actif: aucun (aucune génération réussie) | "
            "llm_real=false | fallback=true | health_state=unavailable"
        )
        if requested_provider:
            print(
                f"Provider '{requested_provider}' not found. Using local fallback replies."
            )
        else:
            print(
                "Automatic provider selection found no available backend. Using local fallback replies."
            )

    psyche = Psyche.load_state(psyche_file)

    def gather_context() -> tuple[
        str | None, dict | None, dict | None, str | None, str | None
    ]:
        signals = capture_signals()
        add_episode({"event": "perception", **signals}, path=episodic_file)
        psyche.consume()
        episodes = read_episodes(episodic_file)
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
        self_narrative_summary: str,
        self_narrative_version: int,
    ) -> str:
        user_signals = _extract_structured_signals(user_input)
        theme = str(user_signals.get("theme", "general"))
        retrieval = MemoryRetrievalService(
            life_root, build_backend(root=mem_dir / "layers")
        )
        recalled_memories = retrieval.retrieve(
            user_input,
            active_objectives=[f"user_dialogue:{theme}"],
            current_context={
                "theme": theme,
                "last_event": last_event,
                "mood": mood_event,
            },
            limit=8,
        )
        recalled_memories = retrieval.within_budget(recalled_memories, 120)
        recall_summary = format_recalled_memories(recalled_memories)
        # General small-talk may reuse immediate context without creating two
        # self-referential audit episodes on every turn.
        if recalled_memories and theme != "general":
            add_episode(
                {
                    "event": "memory.recalled",
                    "source": "talk",
                    "query": user_input,
                    "memories": recalled_memories,
                    "summary": recall_summary,
                },
                path=episodic_file,
            )
            add_episode(
                {
                    "event": "memory.used_for_decision",
                    "source": "talk",
                    "decision": "assistant_reply",
                    "memories": recalled_memories,
                    "summary": recall_summary,
                },
                path=episodic_file,
            )
        add_episode(
            {"role": "user", "text": user_input, "structured_signals": user_signals},
            path=episodic_file,
        )
        mood = psyche.feel(Mood.NEUTRAL)
        mood_report = mood_event or mood.value
        system_preamble = _build_system_preamble(
            narrative_summary=self_narrative_summary,
            last_event=last_event,
            mood_event=mood_event,
            recalled_memory_summary=format_recalled_memories(recalled_memories),
        )
        provider_prompt = f"{system_preamble}\n\nUtilisateur: {user_input}"

        start = time.perf_counter()
        fallback_used = client is None
        error_category: str | None = "provider_missing" if client is None else None
        active_provider: str | None = None
        llm_real = bool(provider_status["llm_real"]) and not fallback_used
        provider_state = "unavailable" if client is None else "ready"

        if client is None:
            print(
                "LLM status: active=none fallback=true mode=dummy "
                f"error_category={error_category} llm_real=false"
            )
            reply = _default_reply(user_input, rng)
        else:
            try:
                reply = client.generate_reply(provider_prompt)
            except LLMProviderError as err:
                fallback_used = True
                llm_real = False
                error_category = getattr(err, "category", "provider_error")
                provider_state = "unavailable"
                print(_user_message_for_error(provider_selection, err))
                print(
                    "LLM status: active=none fallback=true mode=dummy "
                    f"error_category={error_category} llm_real=false"
                )
                reply = _default_reply(user_input, rng)
            else:
                if isinstance(client, FallbackLLMClient):
                    active_provider = client.last_active_provider or active_provider
                    fallback_used = client.last_fallback_used
                    error_category = (
                        client.last_errors[-1]["category"]
                        if client.last_errors
                        else None
                    )
                else:
                    active_provider = client.name
                    fallback_used = False
                    error_category = None
                llm_real = provider_is_real(active_provider)
                if not llm_real:
                    provider_state = "degraded_dummy"
                    reply = f"[RÉPONSE DÉTERMINISTE/FACTICE — provider dummy] {reply}"
                    fallback_used = True
                    print(
                        "Aucun fournisseur LLM réel n'est disponible; le provider "
                        "dummy produit uniquement un écho factice."
                    )
                if isinstance(client, FallbackLLMClient):
                    for failure in client.last_errors:
                        command = PROVIDER_CONFIGURATION_COMMANDS.get(
                            failure["provider"]
                        )
                        print(
                            f"Cause {failure['provider']}: {failure['category']} — "
                            f"{failure['error']}"
                            + (f" | Configuration: `{command}`" if command else "")
                        )
                print(
                    f"LLM status: active={active_provider} "
                    f"fallback={str(fallback_used).lower()} winner={active_provider} "
                    f"error_category={error_category or 'none'} "
                    f"llm_real={str(llm_real).lower()} "
                    f"mode={'llm' if llm_real else 'dummy'}"
                )

        latency_ms = (time.perf_counter() - start) * 1000
        log_provider_event(
            provider=provider_selection,
            latency_ms=latency_ms,
            fallback=fallback_used,
            error_category=error_category,
            llm_real=llm_real,
            active_provider=active_provider,
            life_root=life_root,
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
                "llm_real": llm_real,
                "requested_provider": requested_provider,
                "selected_provider": provider_status["selected_provider"],
                "active_provider": active_provider,
                "fallback_used": fallback_used,
                "health_state": provider_status["health_state"],
                "provider_candidates": provider_status["candidates"],
                "error_category": error_category,
                "provider_state": provider_state,
                "structured_signals": user_signals,
                "context": {
                    "self_narrative_version": self_narrative_version,
                    "self_narrative_summary": _trim_for_budget(
                        self_narrative_summary, 180
                    ),
                    "recalled_memories": recalled_memories,
                    "recalled_memory_summary": recall_summary,
                },
            },
            path=episodic_file,
        )
        gain_estimate = round(
            float(user_signals.get("satisfaction", 0.0))
            - float(user_signals.get("frustration", 0.0)),
            3,
        )
        # A real provider reached through the fallback chain is still real;
        # dummy/echo output, however, must never improve cognitive metrics.
        cognitive_success = llm_real
        cognitive_gain = gain_estimate if cognitive_success else 0.0
        add_causal_trace(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "trace_id": uuid4().hex,
                "pipeline": "interaction.talk",
                "input": {
                    "kind": "human_message",
                    "message": user_input,
                    "structured_signals": user_signals,
                },
                "decision": {
                    "provider": provider_selection,
                    "provider_selection": (
                        "explicit" if requested_provider else "automatic"
                    ),
                    "requested_provider": requested_provider,
                    "selected_provider": provider_status["selected_provider"],
                    "active_provider": active_provider,
                    "fallback_used": fallback_used,
                    "health_state": provider_status["health_state"],
                    "provider_candidates": provider_status["candidates"],
                    "error_category": error_category,
                    "llm_real": llm_real,
                    "provider_state": provider_state,
                    "mood": mood_report,
                    "recalled_memory_summary": recall_summary,
                    "recalled_memories": recalled_memories,
                },
                "action": {
                    "kind": "assistant_reply",
                    "raw_reply": reply,
                    "response": response,
                },
                "result": {
                    "cognitive_success": cognitive_success,
                    "gain_loss": cognitive_gain,
                    "objective_impact": {
                        "objective": f"user_dialogue:{user_signals.get('theme', 'general')}",
                        "impact": cognitive_gain,
                    },
                },
            },
            path=causal_file,
        )
        psyche.gain()
        psyche.save_state(psyche_file)
        return response

    if prompt is not None:
        context = gather_context()
        self_narrative = load_self_narrative(narrative_file)
        return respond(
            prompt,
            *context,
            summarize_short(self_narrative),
            self_narrative.schema_version,
        )
        return

    while True:
        context = gather_context()
        self_narrative = load_self_narrative(narrative_file)
        try:
            user_input = input("you: ")
        except EOFError:
            break
        except KeyboardInterrupt:
            print("\nExiting conversation.")
            break

        if user_input.strip().lower() in {"exit", "quit"}:
            break

        respond(
            user_input,
            *context,
            summarize_short(self_narrative),
            self_narrative.schema_version,
        )
