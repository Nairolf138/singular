"""Read-only access to a predefined sandbox directory."""

from __future__ import annotations

from pathlib import Path
from typing import List

# Root of the sandbox; resolves relative to the current working directory
SANDBOX_ROOT = Path("./sandbox").resolve()


def _resolve(path: str | Path) -> Path:
    """Return the absolute :class:`Path` inside :data:`SANDBOX_ROOT`.

    A :class:`ValueError` is raised if *path* escapes the sandbox directory.
    """

    candidate = (SANDBOX_ROOT / path).resolve()
    if not str(candidate).startswith(str(SANDBOX_ROOT)):
        raise ValueError("attempted access outside sandbox")
    return candidate


def list_files() -> List[str]:
    """Return a list of file names available in the sandbox.

    The paths are returned relative to :data:`SANDBOX_ROOT`.
    """

    if not SANDBOX_ROOT.exists():
        return []
    files: List[str] = []
    for p in SANDBOX_ROOT.rglob("*"):
        if p.is_file():
            files.append(str(p.relative_to(SANDBOX_ROOT)))
    return files


def read_file(path: str | Path, encoding: str = "utf-8") -> str:
    """Return the contents of *path* inside the sandbox.

    The file is opened in text mode using *encoding* and the content is
    returned as a string. Attempts to access paths outside the sandbox raise
    :class:`ValueError`.
    """

    target = _resolve(path)
    if not target.is_file():
        raise FileNotFoundError(path)
    return target.read_text(encoding=encoding)
