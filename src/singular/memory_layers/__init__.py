from .base import MemoryBackend, MemoryRecord
from .local_json import LocalJsonMemoryBackend
from .service import MemoryLayerService
from .retrieval import MemoryRetrievalService, RetrievalResult
from .vector_adapter import build_backend

__all__ = [
    "MemoryBackend",
    "MemoryRecord",
    "LocalJsonMemoryBackend",
    "MemoryLayerService",
    "MemoryRetrievalService",
    "RetrievalResult",
    "build_backend",
    "EmbodimentOutcomePipeline",
]


def __getattr__(name: str):
    # Importing the pipeline eagerly creates a cycle through self_narrative
    # and lives when the installed CLI starts from a fresh Python process.
    if name == "EmbodimentOutcomePipeline":
        from .embodiment_pipeline import EmbodimentOutcomePipeline

        return EmbodimentOutcomePipeline
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
