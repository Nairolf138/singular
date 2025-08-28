"""A tiny subset of the FastAPI interface used for testing.

This lightweight stub provides only the pieces of FastAPI that our
unit tests require.  It avoids the heavy dependency on the real
`fastapi` package which is unavailable in the execution environment.
"""
from __future__ import annotations

from typing import Any, Callable, Dict


class HTTPException(Exception):
    """Exception carrying an HTTP status code."""

    def __init__(self, status_code: int, detail: str | None = None) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class FastAPI:
    """Minimal application object supporting GET routes."""

    def __init__(self) -> None:
        self._routes: Dict[str, Callable[[], Any]] = {}

    def get(self, path: str, **_kwargs: Any) -> Callable[[Callable[[], Any]], Callable[[], Any]]:
        """Register a GET handler for ``path``.

        Extra keyword arguments (such as ``response_class``) are accepted
        for compatibility but ignored.
        """

        def decorator(func: Callable[[], Any]) -> Callable[[], Any]:
            self._routes[path] = func
            return func

        return decorator


# ``TestClient`` lives in a separate submodule to mirror the real package
from .testclient import TestClient  # noqa: E402

__all__ = ["FastAPI", "HTTPException", "TestClient"]
