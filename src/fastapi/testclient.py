"""Simplistic HTTP client for the FastAPI stub."""

from __future__ import annotations

from typing import Any

from . import HTTPException, WebSocket, WebSocketDisconnect
import threading


class Response:
    """Represents a minimal HTTP response object."""

    def __init__(self, status_code: int, data: Any) -> None:
        self.status_code = status_code
        self._data = data

    def json(self) -> Any:  # pragma: no cover - trivial
        return self._data


class TestClient:
    """Very small subset of the real TestClient API used in tests."""

    def __init__(self, app: Any) -> None:
        self.app = app

    def get(self, path: str) -> Response:
        handler = self.app._routes[path]
        try:
            data = handler()
            status = 200
        except HTTPException as exc:  # pragma: no cover - simple error path
            data = None
            status = exc.status_code
        return Response(status, data)

    class _WSConnection:
        def __init__(self, handler: Any) -> None:
            self.ws = WebSocket()
            self._handler = handler
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

        def _run(self) -> None:
            try:
                self._handler(self.ws)
            except WebSocketDisconnect:
                pass

        def receive_json(self) -> Any:
            return self.ws.receive_json()

        def __enter__(self) -> "TestClient._WSConnection":
            return self

        def __exit__(self, *_args: Any) -> None:
            self.ws.close()
            self._thread.join(timeout=0.1)

    def websocket_connect(self, path: str) -> "TestClient._WSConnection":
        handler = self.app._ws_routes[path]
        return TestClient._WSConnection(handler)
