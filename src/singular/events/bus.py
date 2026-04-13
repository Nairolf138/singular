"""Internal publish/subscribe event bus with payload versioning."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
import atexit
import logging
import os
from queue import Empty, Queue
import threading
from typing import Any, Callable

EventHandler = Callable[["Event"], None]
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Event:
    """Event envelope dispatched to subscribers."""

    event_type: str
    payload: dict[str, Any]
    payload_version: int = 1
    emitted_at: str = ""


class EventBus:
    """Simple event bus supporting sync and async dispatch modes."""

    def __init__(self, *, mode: str = "sync", strict: bool = False) -> None:
        normalized_mode = mode.strip().lower()
        if normalized_mode not in {"sync", "async"}:
            normalized_mode = "sync"
        self.mode = normalized_mode
        self.strict = strict
        self._subscribers: dict[str, list[EventHandler]] = defaultdict(list)
        self._lock = threading.Lock()
        self._queue: Queue[Event] | None = None
        self._worker: threading.Thread | None = None
        self._stop_event: threading.Event | None = None
        if self.mode == "async":
            self._start_worker()

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """Register a ``handler`` for ``event_type``."""

        with self._lock:
            handlers = self._subscribers[event_type]
            if handler not in handlers:
                handlers.append(handler)

    def publish(
        self,
        event_type: str,
        payload: dict[str, Any],
        *,
        payload_version: int = 1,
    ) -> None:
        """Publish one event with an explicit payload schema version."""

        event = Event(
            event_type=event_type,
            payload=payload,
            payload_version=payload_version,
            emitted_at=datetime.now(timezone.utc).isoformat(),
        )
        if self.mode == "async":
            if self._queue is None:
                self._start_worker()
            assert self._queue is not None
            self._queue.put(event)
            return
        self._dispatch(event)

    def shutdown(self, *, timeout: float = 1.0) -> None:
        """Stop async worker and flush pending events."""

        if self.mode != "async":
            return
        if self._stop_event is None or self._queue is None or self._worker is None:
            return
        self._stop_event.set()
        self._queue.put(
            Event(event_type="__bus.shutdown__", payload={}, payload_version=1)
        )
        self._worker.join(timeout=timeout)

    def _dispatch(self, event: Event) -> None:
        with self._lock:
            handlers = list(self._subscribers.get(event.event_type, []))
        for handler in handlers:
            try:
                handler(event)
            except Exception:
                logger.exception(
                    "Error while handling event '%s' in handler '%s'",
                    event.event_type,
                    getattr(handler, "__name__", repr(handler)),
                )
                if self.strict:
                    raise

    def _start_worker(self) -> None:
        if self._queue is None:
            self._queue = Queue()
        if self._stop_event is None:
            self._stop_event = threading.Event()
        if self._worker is None or not self._worker.is_alive():
            self._worker = threading.Thread(target=self._run_worker, daemon=True)
            self._worker.start()

    def _run_worker(self) -> None:
        assert self._queue is not None
        assert self._stop_event is not None
        while not self._stop_event.is_set():
            try:
                event = self._queue.get(timeout=0.1)
            except Empty:
                continue
            if event.event_type == "__bus.shutdown__":
                self._queue.task_done()
                break
            self._dispatch(event)
            self._queue.task_done()


_GLOBAL_BUS: EventBus | None = None


def get_bus_mode_from_env() -> str:
    """Read event bus mode from configuration environment."""

    return os.environ.get("SINGULAR_EVENT_BUS_MODE", "sync").strip().lower()


def get_bus_strict_from_env() -> bool:
    """Read strict event bus mode from configuration environment."""

    value = os.environ.get("SINGULAR_EVENT_BUS_STRICT", "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def get_global_event_bus() -> EventBus:
    """Return process-wide event bus configured by environment."""

    global _GLOBAL_BUS
    if _GLOBAL_BUS is None:
        _GLOBAL_BUS = EventBus(
            mode=get_bus_mode_from_env(), strict=get_bus_strict_from_env()
        )
        atexit.register(_GLOBAL_BUS.shutdown)
    return _GLOBAL_BUS
