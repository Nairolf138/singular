"""Shared file I/O helpers with durability and cross-platform locking."""

from __future__ import annotations

from contextlib import contextmanager, nullcontext
from pathlib import Path
from typing import Any, Iterator
import json
import os
import tempfile

if os.name == "nt":
    import msvcrt
else:
    import fcntl


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


@contextmanager
def _locked_file(path: Path) -> Iterator[None]:
    """Acquire an exclusive sidecar lock for ``path``."""

    lock_path = path.with_suffix(path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as lock_file:
        if os.name == "nt":
            lock_file.seek(0)
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
        else:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == "nt":
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def atomic_write_text(path: Path | str, data: str, fsync: bool = True) -> None:
    """Atomically write text to ``path`` using a temporary sibling file."""

    destination = Path(path)
    _ensure_parent(destination)
    tmp = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=destination.parent, delete=False
    )
    try:
        with tmp:
            tmp.write(data)
            tmp.flush()
            if fsync:
                os.fsync(tmp.fileno())
        os.replace(tmp.name, destination)
        if fsync and os.name != "nt":
            dir_fd = os.open(destination.parent, os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
    finally:
        try:
            os.unlink(tmp.name)
        except FileNotFoundError:
            pass


def append_jsonl_line(
    path: Path | str,
    payload: dict[str, Any],
    with_lock: bool = True,
) -> None:
    """Append one JSON object as JSONL with optional cross-platform locking."""

    destination = Path(path)
    _ensure_parent(destination)
    line = json.dumps(payload, ensure_ascii=False) + "\n"
    lock_context = _locked_file(destination) if with_lock else nullcontext()
    with lock_context:
        with destination.open("a", encoding="utf-8") as file:
            file.write(line)
            file.flush()
            os.fsync(file.fileno())
