"""Utilities and shared contracts for LLM providers."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from importlib.metadata import entry_points
import inspect
from typing import Callable, Protocol

DEFAULT_PROVIDER_TIMEOUT_SECONDS = 8.0
DEFAULT_PROVIDER_MAX_RETRIES = 2


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


class ReplyGenerator(Protocol):
    """Runtime protocol for provider generation functions."""

    def __call__(self, prompt: str, *, timeout: float = DEFAULT_PROVIDER_TIMEOUT_SECONDS) -> str:  # pragma: no cover - typing only
        ...


@dataclass
class LLMProviderClient:
    """Common client wrapper exposing timeout and bounded retries."""

    name: str
    generate: Callable[..., str]
    max_retries: int = DEFAULT_PROVIDER_MAX_RETRIES

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


def _invoke_provider(fn: Callable[..., str], *, prompt: str, timeout: float) -> str:
    """Invoke provider callables while supporting legacy signatures."""

    try:
        signature = inspect.signature(fn)
    except (TypeError, ValueError):
        signature = None

    if signature is not None and "timeout" in signature.parameters:
        return fn(prompt, timeout=timeout)
    return fn(prompt)


def load_llm_client(name: str | None) -> LLMProviderClient | None:
    """Load an LLM provider and expose it through :class:`LLMProviderClient`."""

    if not name:
        return None
    module_name = f"singular.providers.llm_{name}"
    try:
        module = import_module(module_name)
        generate = getattr(module, "generate_reply", None)
        if callable(generate):
            retries = getattr(module, "MAX_RETRIES", DEFAULT_PROVIDER_MAX_RETRIES)
            return LLMProviderClient(name=name, generate=generate, max_retries=retries)
    except ModuleNotFoundError:
        pass

    for ep in entry_points(group="singular.llm"):
        if ep.name != name:
            continue
        obj = ep.load()
        generate = getattr(obj, "generate_reply", obj)
        if callable(generate):
            retries = getattr(obj, "MAX_RETRIES", DEFAULT_PROVIDER_MAX_RETRIES)
            return LLMProviderClient(name=name, generate=generate, max_retries=retries)
    return None


def load_llm_provider(name: str | None) -> Callable[[str], str] | None:
    """Backward-compatible loader returning a plain ``generate_reply`` callable."""

    client = load_llm_client(name)
    if client is None:
        return None
    return lambda prompt: client.generate_reply(prompt)
