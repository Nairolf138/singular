from __future__ import annotations

from pathlib import Path
import logging
import os

from .base import MemoryBackend
from .local_json import LocalJsonMemoryBackend

log = logging.getLogger(__name__)


def build_backend(*, root: Path | str | None = None) -> MemoryBackend:
    """Build a memory backend from env config.

    SINGULAR_MEMORY_BACKEND=local|chroma|pinecone
    """

    backend = os.environ.get("SINGULAR_MEMORY_BACKEND", "local").strip().lower()
    root_path = Path(root) if root is not None else Path(
        os.environ.get("SINGULAR_HOME", ".")
    ) / "mem" / "layers"

    if backend == "local":
        return LocalJsonMemoryBackend(root_path)

    if backend == "chroma":
        try:
            import chromadb  # type: ignore  # noqa: F401
        except ImportError:
            log.warning("chroma backend requested but chromadb is missing, fallback local")
            return LocalJsonMemoryBackend(root_path)

    if backend == "pinecone":
        try:
            import pinecone  # type: ignore  # noqa: F401
        except ImportError:
            log.warning("pinecone backend requested but pinecone is missing, fallback local")
            return LocalJsonMemoryBackend(root_path)

    # Adapter stub: until full API wiring, fallback to the local implementation.
    return LocalJsonMemoryBackend(root_path)
