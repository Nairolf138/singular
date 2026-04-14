"""Utilities and shared contracts for LLM providers."""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib import import_module
from importlib.metadata import entry_points
import inspect
import os
from typing import Any, Callable, Protocol

DEFAULT_PROVIDER_TIMEOUT_SECONDS = 8.0
DEFAULT_PROVIDER_MAX_RETRIES = 2
DEFAULT_FALLBACK_CHAIN = ("local", "openai", "dummy")


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

    def __call__(self, prompt: str, *, timeout: float = DEFAULT_PROVIDER_TIMEOUT_SECONDS) -> str:  # pragma: no cover - typing only
        ...


class Embedder(Protocol):
    """Runtime protocol for provider embedding functions."""

    def __call__(self, text: str, *, timeout: float = DEFAULT_PROVIDER_TIMEOUT_SECONDS) -> list[float]:  # pragma: no cover - typing only
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
    metrics: ProviderMetrics = field(default_factory=lambda: ProviderMetrics(provider="unknown"))

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

    def generate_reply(self, prompt: str, *, timeout: float = DEFAULT_PROVIDER_TIMEOUT_SECONDS) -> str:
        last_error: LLMProviderError | None = None
        for client in self.chain:
            try:
                return client.generate_reply(prompt, timeout=timeout)
            except LLMProviderError as exc:
                last_error = exc
                continue
        if last_error is not None:
            raise last_error
        raise ProviderUnavailableError("No provider available in fallback chain")


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
        if callable(generate) and callable(embed) and callable(healthcheck) and callable(cost_estimate):
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
        embed = getattr(obj, "embed", lambda text, timeout=DEFAULT_PROVIDER_TIMEOUT_SECONDS: [float(len(text)), float(timeout)])
        healthcheck = getattr(obj, "healthcheck", lambda: {"ok": True, "provider": name})
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
    for chain_name in chain_names:
        contract = _load_provider_contract(chain_name)
        if contract is None:
            continue
        clients.append(
            LLMProviderClient(
                name=contract.name,
                generate=contract.generate,
                embed=contract.embed,
                healthcheck=contract.healthcheck,
                cost_estimate=contract.cost_estimate,
                max_retries=contract.max_retries,
            )
        )

    if not clients:
        return None
    if len(clients) == 1:
        return clients[0]
    return FallbackLLMClient(
        name=",".join(client.name for client in clients),
        generate=clients[0].generate,
        embed=clients[0].embed,
        healthcheck=clients[0].healthcheck,
        cost_estimate=clients[0].cost_estimate,
        max_retries=0,
        chain=clients,
    )


def load_llm_provider(name: str | None) -> Callable[[str], str] | None:
    """Backward-compatible loader returning a plain ``generate_reply`` callable."""

    client = load_llm_client(name)
    if client is None:
        return None
    return lambda prompt: client.generate_reply(prompt)
