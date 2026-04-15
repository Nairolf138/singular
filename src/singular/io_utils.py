"""Shared file I/O helpers with durability and cross-platform locking."""

from __future__ import annotations

from contextlib import contextmanager, nullcontext
from pathlib import Path
from typing import Any, Iterator
import json
import os
import tempfile
import time

if os.name == "nt":
    import msvcrt
else:
    import fcntl

_DEFAULT_REPLACE_MAX_ATTEMPTS = 6
_DEFAULT_REPLACE_INITIAL_DELAY_SECONDS = 0.025
_DEFAULT_REPLACE_MAX_DELAY_SECONDS = 0.2
_WINDOWS_REPLACE_MAX_ATTEMPTS = 8
_WINDOWS_REPLACE_MAX_DELAY_SECONDS = 0.4


def _is_windows() -> bool:
    return os.name == "nt"


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


@contextmanager
def _locked_file(path: Path) -> Iterator[None]:
    """Acquire an exclusive sidecar lock for ``path``."""

    lock_path = path.with_suffix(path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as lock_file:
        if _is_windows():
            lock_file.seek(0)
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
        else:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if _is_windows():
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


@contextmanager
def file_lock(path: Path | str) -> Iterator[None]:
    """Public lock helper using the same sidecar strategy as JSONL append."""

    with _locked_file(Path(path)):
        yield


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
        _replace_with_retry(tmp.name, destination)
        if fsync and not _is_windows():
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


def _replace_with_retry(source: str, destination: Path) -> None:
    """Replace ``destination`` with ``source``, retrying transient Windows lock errors."""

    max_attempts = (
        _WINDOWS_REPLACE_MAX_ATTEMPTS if _is_windows() else _DEFAULT_REPLACE_MAX_ATTEMPTS
    )
    delay_seconds = _DEFAULT_REPLACE_INITIAL_DELAY_SECONDS
    max_delay_seconds = (
        _WINDOWS_REPLACE_MAX_DELAY_SECONDS
        if _is_windows()
        else _DEFAULT_REPLACE_MAX_DELAY_SECONDS
    )
    first_exception: PermissionError | OSError | None = None
    observed_delays: list[float] = []

    for attempt in range(1, max_attempts + 1):
        try:
            os.replace(source, destination)
            return
        except PermissionError as exc:
            if not _is_windows():
                raise
            if first_exception is None:
                first_exception = exc
        except OSError as exc:
            if not _is_windows() or getattr(exc, "winerror", None) != 5:
                raise
            if first_exception is None:
                first_exception = exc

        if attempt < max_attempts:
            observed_delays.append(delay_seconds)
            time.sleep(delay_seconds)
            delay_seconds = min(delay_seconds * 2, max_delay_seconds)

    assert first_exception is not None  # pragma: no cover - defensive

    with _locked_file(destination):
        try:
            os.replace(source, destination)
            return
        except PermissionError as exc:
            if not _is_windows():
                raise
            fallback_exception: PermissionError | OSError = exc
        except OSError as exc:
            if not _is_windows() or getattr(exc, "winerror", None) != 5:
                raise
            fallback_exception = exc

    fallback_exception.add_note(
        "atomic_write_text failed after retry loop and sidecar-lock fallback "
        f"(source={source!r}, destination={str(destination)!r}, attempts={max_attempts}, "
        f"delays={observed_delays!r})."
    )
    raise fallback_exception


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
