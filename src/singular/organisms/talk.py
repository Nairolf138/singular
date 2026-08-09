"""Talk command implementation."""

from __future__ import annotations

import os
import random
import time
import json
from dataclasses import dataclass, field
from typing import Mapping, Any, Iterable
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
from ..perception.interaction import apply_psyche_deltas, extract_structured_signals
from ..psyche import Mood, Psyche
from ..identity.synchronization import IdentitySynchronizationService
from ..self_narrative import load as load_self_narrative, summarize_short
from ..lives import canonical_life_id
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

_UNKNOWN_GUARD = 'Garde anti-hallucination: si une information demandée est inconnue, réponds explicitement "inconnu".'


@dataclass(frozen=True)
class ContextBudget:
    """Deterministic, character-based prompt budget with per-section limits."""

    total: int = 420
    identity: int = 220
    traits: int = 100
    values: int = 100
    objectives: int = 100
    relations: int = 100
    recent_events: int = 100
    recalled_memories: int = 120
    safety: int = 160

    @classmethod
    def for_client(cls, client: object | None) -> "ContextBudget":
        provider = str(getattr(client, "name", "") or "").lower()
        model = str(getattr(client, "model", "") or "").lower()
        # Conservative defaults are intentionally stable.  Larger local context
        # windows may opt into more context, but never beyond the hard ceiling.
        total = {"ollama": 900, "local": 700}.get(provider, 420)
        if any(marker in model for marker in ("32k", "128k", "200k")):
            total = 1200
        configured = os.getenv("SINGULAR_TALK_CONTEXT_CHARS")
        if configured:
            try:
                total = int(configured)
            except ValueError:
                pass
        total = max(len(_UNKNOWN_GUARD) + 20, min(total, 2000))
        scale = total / 420
        return cls(
            total=total,
            identity=round(220 * scale),
            traits=round(100 * scale),
            values=round(100 * scale),
            objectives=round(100 * scale),
            relations=round(100 * scale),
            recent_events=round(100 * scale),
            recalled_memories=round(120 * scale),
            safety=round(160 * scale),
        )


@dataclass(frozen=True)
class ContextItem:
    section: str
    text: str
    provenance_id: str
    relevance: float = 0.0
    recency: float = 0.0
    confidence: float = 1.0
    active_life: bool = True
    critical: bool = False

    @property
    def priority(self) -> tuple[float, float, float, int, str]:
        return (
            self.relevance,
            self.recency,
            self.confidence,
            int(self.active_life),
            self.provenance_id,
        )


@dataclass
class ContextBuildResult:
    text: str
    metrics: dict[str, Any] = field(default_factory=dict)


_SECTION_LABELS = {
    "identity": "Contexte identitaire",
    "traits": "Traits",
    "values": "Valeurs",
    "objectives": "Objectifs",
    "relations": "Relations",
    "recent_events": "Événements récents",
    "recalled_memories": "Souvenirs récupérés",
    "safety": "Règle de sécurité",
}


def _build_structured_context(
    items: Iterable[ContextItem], budget: ContextBudget
) -> ContextBuildResult:
    """Select complete facts only; safety is pinned and no text is sliced."""
    limits = {name: getattr(budget, name) for name in _SECTION_LABELS}
    ordered = sorted(items, key=lambda item: item.priority, reverse=True)
    safety = [item for item in ordered if item.section == "safety"]
    others = [item for item in ordered if item.section != "safety"]
    selected: list[ContextItem] = []
    dropped: list[ContextItem] = []
    section_sizes = {name: 0 for name in limits}
    total = 0
    # Safety rules are indivisible and retained before all autobiographical data.
    for item in safety + others:
        rendered = (
            f"{_SECTION_LABELS[item.section]}: [{item.provenance_id}] {item.text}\n"
        )
        size = len(rendered)
        fits = (
            section_sizes[item.section] + size <= limits[item.section]
            and total + size <= budget.total
        )
        if fits or (item.critical and item.section == "safety"):
            selected.append(item)
            section_sizes[item.section] += size
            total += size
        else:
            dropped.append(item)
    text = "".join(
        f"{_SECTION_LABELS[item.section]}: [{item.provenance_id}] {item.text}\n"
        for item in selected
    ).rstrip()
    return ContextBuildResult(
        text,
        {
            "budget_chars": budget.total,
            "used_chars": len(text),
            "estimated_tokens": (len(text) + 3) // 4,
            "blocks": {
                name: {
                    "chars": section_sizes[name],
                    "estimated_tokens": (section_sizes[name] + 3) // 4,
                }
                for name in limits
            },
            # IDs and counts are auditable without copying potentially sensitive text.
            "retained_ids": [item.provenance_id for item in selected],
            "dropped_ids": [item.provenance_id for item in dropped],
            "retained_count": len(selected),
            "dropped_count": len(dropped),
        },
    )


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


def _trim_for_budget(text: str, budget: int) -> str:
    cleaned = " ".join(text.split())
    if budget <= 3:
        return cleaned[:budget]
    if len(cleaned) <= budget:
        return cleaned
    return f"{cleaned[: budget - 3]}..."


def _load_context_profile(life_root: Path, narrative_summary: str) -> list[ContextItem]:
    """Read stable profile sections without exposing their values to telemetry."""
    items = [
        ContextItem(
            "identity", narrative_summary, "self_narrative:summary", relevance=1.1
        )
    ]
    sources = (
        (life_root / "id.json", ("identity",)),
        (
            life_root / "mem" / "self_model.json",
            ("traits", "values", "objectives", "relations"),
        ),
    )
    aliases = {
        "identity": ("identity", "name", "id"),
        "traits": ("traits", "preferences"),
        "values": ("values", "identity_commitments", "constraints"),
        "objectives": ("objectives", "goals"),
        "relations": ("relations", "social"),
    }
    for path, sections in sources:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            continue
        if not isinstance(raw, Mapping):
            continue
        for section in sections:
            payload = {key: raw[key] for key in aliases[section] if key in raw}
            if not payload:
                continue
            text = json.dumps(
                payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )
            items.append(
                ContextItem(
                    section,
                    text,
                    f"{path.name}:{section}",
                    relevance=1.0,
                    confidence=1.0,
                )
            )
    return items


def _build_system_preamble(
    *,
    narrative_summary: str,
    last_event: str | None,
    mood_event: str | None,
    recalled_memory_summary: str | None = None,
    budget: ContextBudget | None = None,
) -> str:
    """Compatibility wrapper for callers that only have the legacy inputs."""
    items = [
        ContextItem(
            "identity", narrative_summary, "self_narrative:summary", relevance=1.1
        ),
        ContextItem(
            "recent_events", last_event or "inconnu", "episode:last_user", recency=1.0
        ),
        ContextItem(
            "recent_events", mood_event or "inconnu", "psyche:recent_mood", recency=0.9
        ),
        ContextItem(
            "recalled_memories",
            recalled_memory_summary or "aucun souvenir pertinent",
            "memory:summary",
            relevance=0.8,
        ),
        ContextItem(
            "safety",
            _UNKNOWN_GUARD,
            "policy:anti_hallucination",
            relevance=1.0,
            critical=True,
        ),
    ]
    return _build_structured_context(items, budget or ContextBudget()).text


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
    life_id = canonical_life_id(life_root.resolve())
    ensure_memory_structure(mem_dir)
    identity_sync = IdentitySynchronizationService(life_root)

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

    def gather_context() -> (
        tuple[str | None, dict | None, dict | None, str | None, str | None]
    ):
        signals = capture_signals()
        add_episode(
            {"event": "perception", "life_id": life_id, **signals}, path=episodic_file
        )
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
        # One identifier joins the human turn, every provider attempt, the
        # resulting narrative evidence and the causal trace.
        correlation_id = uuid4().hex
        user_signals = extract_structured_signals(
            user_input, state_path=mem_dir / "interaction_perception.json"
        )
        apply_psyche_deltas(psyche, user_signals)
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
                    "life_id": life_id,
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
                    "life_id": life_id,
                    "source": "talk",
                    "decision": "assistant_reply",
                    "memories": recalled_memories,
                    "summary": recall_summary,
                },
                path=episodic_file,
            )
        add_episode(
            {
                "role": "user",
                "life_id": life_id,
                "text": user_input,
                "structured_signals": user_signals,
            },
            path=episodic_file,
        )
        mood = psyche.feel(Mood.NEUTRAL)
        mood_report = mood_event or mood.value
        context_items = _load_context_profile(life_root, self_narrative_summary)
        context_items.extend(
            [
                ContextItem(
                    "recent_events",
                    last_event or "inconnu",
                    "episode:last_user",
                    recency=1.0,
                ),
                ContextItem(
                    "recent_events",
                    mood_event or "inconnu",
                    "psyche:recent_mood",
                    recency=0.9,
                ),
                ContextItem(
                    "safety",
                    _UNKNOWN_GUARD,
                    "policy:anti_hallucination",
                    relevance=1.0,
                    critical=True,
                ),
            ]
        )
        for memory in recalled_memories:
            provenance = (
                f"{memory.get('source', 'memory')}:{memory.get('id', 'unknown')}"
            )
            context_items.append(
                ContextItem(
                    "recalled_memories",
                    str(memory.get("excerpt", "")),
                    provenance,
                    relevance=float(memory.get("score", 0.0) or 0.0),
                    recency=1.0 if memory.get("date") else 0.0,
                    confidence=float(memory.get("confidence", 0.0) or 0.0),
                    active_life=memory.get("life_id", life_id) == life_id,
                )
            )
        context_result = _build_structured_context(
            context_items, ContextBudget.for_client(client)
        )
        system_preamble = context_result.text
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
            context_metrics=context_result.metrics,
            correlation_id=correlation_id,
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
                "correlation_id": correlation_id,
                "life_id": life_id,
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
                    "metrics": context_result.metrics,
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
                "correlation_id": correlation_id,
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
                    "context_metrics": context_result.metrics,
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
        identity_sync.apply_event(
            {
                "event_id": f"conversation-{correlation_id}",
                "correlation_id": correlation_id,
                "source": "organisms.talk",
                "type": "conversation",
                "summary": "Interaction utilisateur traitée",
            },
            psyche=psyche,
        )
        return response

    if prompt is not None:
        context = gather_context()
        self_narrative = load_self_narrative(narrative_file, life_id=life_id)
        return respond(
            prompt,
            *context,
            summarize_short(self_narrative),
            self_narrative.schema_version,
        )
        return

    while True:
        context = gather_context()
        self_narrative = load_self_narrative(narrative_file, life_id=life_id)
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
