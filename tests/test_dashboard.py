import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from singular.dashboard import create_app, run


def test_dashboard_endpoints(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    (runs_dir / "log.txt").write_text("hello")
    psyche_file = tmp_path / "psyche.json"
    data = {"mood": "happy"}
    psyche_file.write_text(json.dumps(data))

    app = create_app(runs_dir=runs_dir, psyche_file=psyche_file)
    client = TestClient(app)

    assert client.get("/logs").json() == {"log.txt": "hello"}
    assert client.get("/psyche").json() == data


def test_psyche_missing_returns_404(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()

    app = create_app(runs_dir=runs_dir, psyche_file=tmp_path / "psyche.json")
    client = TestClient(app)

    response = client.get("/psyche")
    assert response.status_code == 404


def test_websocket_stream(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    log_file = runs_dir / "log.txt"
    log_file.write_text("hello")
    psyche_file = tmp_path / "psyche.json"
    psyche_file.write_text(json.dumps({"mood": "happy"}))

    app = create_app(runs_dir=runs_dir, psyche_file=psyche_file)
    client = TestClient(app)

    with client.websocket_connect("/ws") as ws:
        first = ws.receive_json()
        second = ws.receive_json()
        received = {first["type"]: first["data"], second["type"]: second["data"]}
        assert received["psyche"] == {"mood": "happy"}
        assert received["logs"] == {"log.txt": "hello"}

        log_file.write_text("bye")
        psyche_file.write_text(json.dumps({"mood": "sad"}))

        msg_a = ws.receive_json()
        msg_b = ws.receive_json()
        updates = {msg_a["type"]: msg_a["data"], msg_b["type"]: msg_b["data"]}
        assert updates["logs"] == {"log.txt": "bye"}
        assert updates["psyche"] == {"mood": "sad"}


def test_run_requires_uvicorn(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import builtins

    real_import = builtins.__import__

    def fake_import(name: str, *args, **kwargs):
        if name == "uvicorn":
            raise ImportError("No module named 'uvicorn'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(SystemExit):
        run()

    captured = capsys.readouterr()
    assert "pip install uvicorn" in captured.err
