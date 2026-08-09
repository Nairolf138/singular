"""Utilities and shared contracts for LLM providers."""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib import import_module
from importlib.metadata import entry_points
import inspect
import os
import queue
import threading
from typing import Any, Callable, Protocol

DEFAULT_PROVIDER_TIMEOUT_SECONDS = 8.0
DEFAULT_PROVIDER_MAX_RETRIES = 2
DEFAULT_HEALTHCHECK_TIMEOUT_SECONDS = 2.0
# Automatic selection prefers a locally managed Ollama model, then the built-in
# local backend, before trying the remote OpenAI service and deterministic dummy.
DEFAULT_FALLBACK_CHAIN = ("ollama", "local", "openai", "dummy")

PROVIDER_CONFIGURATION_COMMANDS = {
    "openai": "singular config openai",
    "ollama": "ollama serve",
    "local": "singular config providers doctor",
    "dummy": "singular config providers doctor",
}


class LLMProviderError(RuntimeError):
    """Base class for provider-facing errors."""

    category = "provider_error"


class ProviderUnavailableError(LLMProviderError):
    """The provider cannot currently be reached or initialized."""

    category = "unavailable"


class ProviderMisconfiguredError(LLMProviderError):
    """The provider is configured incorrectly."""

    category = "misconfigured"


class ProviderQuotaExceededError(LLMProviderError):
    """The provider rejected the request due to quota/rate limits."""

    category = "quota_exceeded"


class ProviderTimeoutError(LLMProviderError):
    """The provider timed out while serving a request."""

    category = "timeout"


class ProviderExecutionError(LLMProviderError):
    """The provider failed for an unknown runtime reason."""

    category = "execution_error"


class ProviderRetryExhaustedError(LLMProviderError):
    """Retry budget has been exhausted for transient provider failures."""

    category = "retry_exhausted"


@dataclass
class ProviderMetrics:
    """Normalized provider metrics attached to provider operations."""

    provider: str
    latency_ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0.0


class ReplyGenerator(Protocol):
    """Runtime protocol for provider generation functions."""

    def __call__(
        self, prompt: str, *, timeout: float = DEFAULT_PROVIDER_TIMEOUT_SECONDS
    ) -> str:  # pragma: no cover - typing only
        ...


class Embedder(Protocol):
    """Runtime protocol for provider embedding functions."""

    def __call__(
        self, text: str, *, timeout: float = DEFAULT_PROVIDER_TIMEOUT_SECONDS
    ) -> list[float]:  # pragma: no cover - typing only
        ...


@dataclass
class LLMProviderContract:
    """Unified provider contract shared by all LLM backends."""

    name: str
    generate: Callable[..., str]
    embed: Callable[..., list[float]]
    healthcheck: Callable[[], dict[str, Any]]
    cost_estimate: Callable[..., float]
    max_retries: int = DEFAULT_PROVIDER_MAX_RETRIES


@dataclass
class LLMProviderClient:
    """Common client wrapper exposing timeout and bounded retries."""

    name: str
    generate: Callable[..., str]
    embed: Callable[..., list[float]] | None = None
    healthcheck: Callable[[], dict[str, Any]] | None = None
    cost_estimate: Callable[..., float] | None = None
    max_retries: int = DEFAULT_PROVIDER_MAX_RETRIES
    metrics: ProviderMetrics = field(
        default_factory=lambda: ProviderMetrics(provider="unknown")
    )
    requested_provider: str | None = None
    selected_provider: str | None = None
    health_state: str = "unknown"
    candidates: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.metrics.provider == "unknown":
            self.metrics.provider = self.name

    def generate_reply(
        self,
        prompt: str,
        *,
        timeout: float = DEFAULT_PROVIDER_TIMEOUT_SECONDS,
    ) -> str:
        attempts = self.max_retries + 1
        last_error: LLMProviderError | None = None

        for attempt in range(1, attempts + 1):
            try:
                return _invoke_provider(self.generate, prompt=prompt, timeout=timeout)
            except ProviderTimeoutError as exc:
                last_error = exc
            except ProviderExecutionError as exc:
                last_error = exc
            except LLMProviderError:
                raise

            if attempt == attempts:
                break

        raise ProviderRetryExhaustedError(
            f"Provider '{self.name}' failed after {attempts} attempts"
        ) from last_error


@dataclass
class FallbackLLMClient(LLMProviderClient):
    """Client that tries multiple providers in order."""

    chain: list[LLMProviderClient] = field(default_factory=list)
    last_active_provider: str | None = field(default=None, init=False)
    last_fallback_used: bool = field(default=False, init=False)
    last_errors: list[dict[str, str]] = field(default_factory=list, init=False)

    def generate_reply(
        self, prompt: str, *, timeout: float = DEFAULT_PROVIDER_TIMEOUT_SECONDS
    ) -> str:
        # These values describe one generation only; do not leak the winner or
        # failures from a previous call when this instance is reused.
        self.last_active_provider = None
        self.last_fallback_used = False
        self.last_errors = []
        last_error: LLMProviderError | None = None
        for index, client in enumerate(self.chain):
            try:
                reply = client.generate_reply(prompt, timeout=timeout)
            except LLMProviderError as exc:
                last_error = exc
                self.last_errors.append(
                    {
                        "provider": client.name,
                        "category": getattr(exc, "category", "provider_error"),
                        "error": str(exc),
                    }
                )
                continue
            self.last_active_provider = client.name
            self.last_fallback_used = index > 0
            return reply
        if last_error is not None:
            raise last_error
        raise ProviderUnavailableError("No provider available in fallback chain")


def provider_is_real(name: str | None) -> bool:
    """Return whether a provider name points to a real LLM backend."""

    if not name:
        return False
    return name.strip().lower() not in {"stub", "dummy"}


def describe_client(
    client: LLMProviderClient | None, requested: str | None
) -> dict[str, Any]:
    """Return status details for a loaded provider client."""

    selected = (
        getattr(client, "selected_provider", None) or getattr(client, "name", None)
        if client is not None
        else None
    )
    chain = (
        [child.name for child in client.chain]
        if isinstance(client, FallbackLLMClient)
        else ([client.name] if client else [])
    )
    has_real = (
        any(provider_is_real(name) for name in chain)
        if chain
        else provider_is_real(selected)
    )
    state = (
        "ready"
        if has_real
        else ("degraded_dummy" if selected == "dummy" else "unavailable")
    )
    return {
        "requested_provider": requested,
        "selected_provider": selected,
        # A backend only becomes active after generate_reply succeeds.
        "active_provider": getattr(client, "last_active_provider", None),
        "fallback_used": getattr(client, "last_fallback_used", False),
        "health_state": (
            getattr(client, "health_state", "unknown") if client else "unavailable"
        ),
        "candidates": getattr(client, "candidates", []) if client else [],
        "provider_chain": chain,
        "llm_real": has_real,
        "state": state,
    }


def doctor_providers(names: list[str] | None = None) -> list[dict[str, Any]]:
    """Healthcheck configured providers without issuing a conversational success signal."""

    provider_names = names or ["openai", "ollama", "local", "dummy"]
    results: list[dict[str, Any]] = []
    for name in provider_names:
        try:
            contract = _load_provider_contract(name)
            if contract is None:
                results.append(
                    {
                        "provider": name,
                        "installed": False,
                        "configured": False,
                        "reachable": False,
                        "degraded": False,
                        "ok": False,
                        "llm_real": provider_is_real(name),
                        "error_category": "provider_missing",
                        "state": "unavailable",
                        "configuration_command": PROVIDER_CONFIGURATION_COMMANDS.get(
                            name
                        ),
                        "cause": "provider implementation not installed",
                    }
                )
                continue
            status = _bounded_healthcheck(contract.healthcheck)
            ok = bool(status.get("ok"))
            real = provider_is_real(name)
            state = (
                "ready" if ok and real else ("degraded_dummy" if ok else "unavailable")
            )
            error = status.get("error")
            category = status.get("error_category") or (
                None
                if ok
                else (
                    "misconfigured"
                    if isinstance(error, str)
                    and (
                        "missing" in error.lower()
                        or "not configured" in error.lower()
                        or ("model" in error.lower() and "not found" in error.lower())
                    )
                    else "unavailable"
                )
            )
            results.append(
                {
                    **status,
                    "provider": str(status.get("provider") or name),
                    "installed": True,
                    "configured": category != "misconfigured",
                    "reachable": ok,
                    "degraded": state == "degraded_dummy",
                    "ok": ok,
                    "llm_real": real,
                    "error_category": category,
                    "state": state,
                    "configuration_command": PROVIDER_CONFIGURATION_COMMANDS.get(name),
                    "cause": None if ok else str(error or "healthcheck failed"),
                }
            )
        except LLMProviderError as exc:
            results.append(
                {
                    "provider": name,
                    "installed": True,
                    "configured": getattr(exc, "category", "") != "misconfigured",
                    "reachable": False,
                    "degraded": False,
                    "ok": False,
                    "llm_real": provider_is_real(name),
                    "error_category": getattr(exc, "category", "provider_error"),
                    "error": str(exc),
                    "state": "unavailable",
                    "configuration_command": PROVIDER_CONFIGURATION_COMMANDS.get(name),
                    "cause": str(exc),
                }
            )
        except Exception as exc:  # defensive: diagnostics must report every provider
            results.append(
                {
                    "provider": name,
                    "installed": True,
                    "configured": False,
                    "reachable": False,
                    "degraded": False,
                    "ok": False,
                    "llm_real": False,
                    "error_category": "unavailable",
                    "error": str(exc),
                    "state": "unavailable",
                    "configuration_command": PROVIDER_CONFIGURATION_COMMANDS.get(name),
                    "cause": str(exc),
                }
            )
    return results


def _bounded_healthcheck(
    healthcheck: Callable[[], dict[str, Any]],
    timeout: float = DEFAULT_HEALTHCHECK_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Run a healthcheck with a hard caller-side deadline.

    The daemon worker deliberately cannot hold process shutdown hostage when a
    third-party healthcheck ignores its own network timeout.
    """

    result: queue.Queue[tuple[bool, Any]] = queue.Queue(maxsize=1)

    def run() -> None:
        try:
            result.put((True, healthcheck()))
        except BaseException as exc:  # returned as diagnostic, never leaked
            result.put((False, exc))

    threading.Thread(target=run, daemon=True, name="provider-healthcheck").start()
    try:
        succeeded, value = result.get(timeout=max(0.001, timeout))
    except queue.Empty:
        return {
            "ok": False,
            "error": f"healthcheck timed out after {timeout:g}s",
            "error_category": "timeout",
        }
    if not succeeded:
        raise value
    if not isinstance(value, dict):
        return {"ok": False, "error": "invalid healthcheck response"}
    return value


def provider_diagnostics(names: list[str] | None = None) -> dict[str, Any]:
    """Return provider details and the effective three-state LLM availability."""

    providers = doctor_providers(names)
    if any(item["state"] == "ready" for item in providers):
        state = "ready"
    elif any(item["state"] == "degraded_dummy" for item in providers):
        state = "degraded_dummy"
    else:
        state = "unavailable"
    return {
        "state": state,
        "llm_real": state == "ready",
        "deterministic_fake": state == "degraded_dummy",
        "providers": providers,
    }


def _invoke_provider(fn: Callable[..., Any], **kwargs: Any) -> Any:
    """Invoke provider callables while supporting legacy signatures."""

    prompt = kwargs.get("prompt")
    timeout = kwargs.get("timeout", DEFAULT_PROVIDER_TIMEOUT_SECONDS)

    try:
        signature = inspect.signature(fn)
    except (TypeError, ValueError):
        signature = None

    if signature is not None and "timeout" in signature.parameters:
        return fn(prompt, timeout=timeout)
    return fn(prompt)


def _resolve_provider_chain(name: str | None) -> list[str]:
    if name:
        parts = [part.strip() for part in name.split(",") if part.strip()]
        if parts:
            return parts
    chain = os.getenv("LLM_PROVIDER_FALLBACK", "")
    if chain.strip():
        return [part.strip() for part in chain.split(",") if part.strip()]
    return list(DEFAULT_FALLBACK_CHAIN)


def _load_provider_contract(name: str) -> LLMProviderContract | None:
    module_name = f"singular.providers.llm_{name}"
    try:
        module = import_module(module_name)
        generate = getattr(module, "generate", getattr(module, "generate_reply", None))
        embed = getattr(module, "embed", None)
        healthcheck = getattr(module, "healthcheck", None)
        cost_estimate = getattr(module, "cost_estimate", None)
        if (
            callable(generate)
            and callable(embed)
            and callable(healthcheck)
            and callable(cost_estimate)
        ):
            retries = getattr(module, "MAX_RETRIES", DEFAULT_PROVIDER_MAX_RETRIES)
            return LLMProviderContract(
                name=name,
                generate=generate,
                embed=embed,
                healthcheck=healthcheck,
                cost_estimate=cost_estimate,
                max_retries=retries,
            )
    except ModuleNotFoundError as exc:
        if exc.name == module_name:
            pass
        else:
            raise ProviderMisconfiguredError(
                f"Provider '{name}' imports missing dependency '{exc.name}'"
            ) from exc

    for ep in entry_points(group="singular.llm"):
        if ep.name != name:
            continue
        obj = ep.load()
        generate = getattr(obj, "generate", getattr(obj, "generate_reply", obj))
        embed = getattr(
            obj,
            "embed",
            lambda text, timeout=DEFAULT_PROVIDER_TIMEOUT_SECONDS: [
                float(len(text)),
                float(timeout),
            ],
        )
        healthcheck = getattr(
            obj, "healthcheck", lambda: {"ok": True, "provider": name}
        )
        cost_estimate = getattr(obj, "cost_estimate", lambda prompt, completion="": 0.0)
        if callable(generate):
            retries = getattr(obj, "MAX_RETRIES", DEFAULT_PROVIDER_MAX_RETRIES)
            return LLMProviderContract(
                name=name,
                generate=generate,
                embed=embed,
                healthcheck=healthcheck,
                cost_estimate=cost_estimate,
                max_retries=retries,
            )
    return None


def load_llm_client(name: str | None) -> LLMProviderClient | None:
    """Load one provider or a configured fallback chain as :class:`LLMProviderClient`."""

    chain_names = _resolve_provider_chain(name)
    clients: list[LLMProviderClient] = []
    candidates: list[dict[str, Any]] = []
    automatic = not bool(name)
    for chain_name in chain_names:
        contract = _load_provider_contract(chain_name)
        if contract is None:
            candidates.append(
                {
                    "provider": chain_name,
                    "installed": False,
                    "configured": False,
                    "reachable": False,
                    "degraded": False,
                    "health_state": "unavailable",
                    "exclusion_cause": "provider implementation not installed",
                }
            )
            continue
        status = (
            _bounded_healthcheck(contract.healthcheck) if automatic else {"ok": True}
        )
        ok = bool(status.get("ok"))
        error = str(status.get("error") or "healthcheck failed")
        misconfigured = not ok and (
            "missing" in error.lower()
            or "not configured" in error.lower()
            or "model" in error.lower()
            and "not found" in error.lower()
        )
        degraded = ok and not provider_is_real(chain_name)
        candidates.append(
            {
                "provider": chain_name,
                "installed": True,
                "configured": not misconfigured,
                "reachable": ok,
                "degraded": degraded,
                "health_state": (
                    "degraded" if degraded else ("ready" if ok else "unavailable")
                ),
                "exclusion_cause": None if ok else error,
            }
        )
        if automatic and not ok:
            continue
        clients.append(
            LLMProviderClient(
                name=contract.name,
                generate=contract.generate,
                embed=contract.embed,
                healthcheck=contract.healthcheck,
                cost_estimate=contract.cost_estimate,
                max_retries=contract.max_retries,
                requested_provider=name,
                selected_provider=contract.name,
                health_state="degraded" if degraded else "ready",
                candidates=candidates,
            )
        )

    if not clients:
        return None
    if len(clients) == 1:
        clients[0].candidates = candidates
        return clients[0]
    return FallbackLLMClient(
        name=",".join(client.name for client in clients),
        generate=clients[0].generate,
        embed=clients[0].embed,
        healthcheck=clients[0].healthcheck,
        cost_estimate=clients[0].cost_estimate,
        max_retries=0,
        chain=clients,
        requested_provider=name,
        selected_provider=clients[0].name,
        health_state=(
            "degraded"
            if all(not provider_is_real(c.name) for c in clients)
            else "ready"
        ),
        candidates=candidates,
    )


def load_llm_provider(name: str | None) -> Callable[[str], str] | None:
    """Backward-compatible loader returning a plain ``generate_reply`` callable."""

    client = load_llm_client(name)
    if client is None:
        return None
    return lambda prompt: client.generate_reply(prompt)
