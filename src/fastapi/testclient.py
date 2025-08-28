"""Simplistic HTTP client for the FastAPI stub."""

from __future__ import annotations

from typing import Any

from . import HTTPException


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
