from __future__ import annotations

from pathlib import Path

import tomllib


def test_dashboard_extra_declares_testclient_compatible_httpx_range() -> None:
    """Keep TestClient's transport dependency in the dashboard extra.

    FastAPI 0.110 permits Starlette 0.36.x, whose TestClient still passes the
    removed ``app=`` argument to httpx and therefore needs httpx below 0.28.
    The 0.27 lower bound also covers newer Starlette releases permitted by the
    project's intentionally broad FastAPI range.
    """

    pyproject_path = Path(__file__).resolve().parents[1] / "pyproject.toml"
    metadata = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    dashboard = metadata["project"]["optional-dependencies"]["dashboard"]

    assert "fastapi>=0.110,<1" in dashboard
    assert "httpx>=0.27,<0.28" in dashboard
