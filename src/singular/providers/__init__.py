"""Utilities for loading LLM providers."""

from __future__ import annotations

from importlib import import_module
from typing import Callable


def load_llm_provider(name: str | None) -> Callable[[str], str] | None:
    """Load an LLM provider's ``generate_reply`` function.

    Parameters
    ----------
    name:
        Provider name suffix, looked up as ``llm_<name>`` in this package.
    """
    if not name:
        return None
    module_name = f"singular.providers.llm_{name}"
    try:
        module = import_module(module_name)
    except ModuleNotFoundError:
        return None
    return getattr(module, "generate_reply", None)
