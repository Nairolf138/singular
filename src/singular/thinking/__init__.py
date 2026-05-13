"""Thinking helpers integrated with the :mod:`singular` package.

The former top-level ``thinking/`` helpers now live under
``singular.thinking`` so they are included by the src-layout package build.
"""

from .memory import EpisodicMemory
from .reasoner import evaluate_actions

__all__ = ["EpisodicMemory", "evaluate_actions"]
