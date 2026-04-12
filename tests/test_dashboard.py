import json
from pathlib import Path
from queue import Empty

import pytest
from fastapi_stub import TestClient

from singular.dashboard import create_app, run


def _receive_with_timeout(ws: TestClient._WSConnection, timeout: float = 2.0) -> dict[str, object]:
    try:
        return ws.ws._queue.get(timeout=timeout)
    except Empty as exc:  # pragma: no cover - defensive for slow CI
        raise AssertionError("timed out waiting for websocket message") from exc


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
    assert client.get("/alerts").json() == {"run": None, "alerts": []}


def test_dashboard_alerts_endpoint(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    run_file = runs_dir / "loop.jsonl"
    lines = []
    for i in range(12):
        lines.append(
            json.dumps(
                {
                    "accepted": False,
                    "health": {
                        "score": 80.0 - i,
                        "sandbox_stability": 0.95 - (i * 0.05),
                    },
                }
            )
        )
    run_file.write_text("\n".join(lines) + "\n")
    psyche_file = tmp_path / "psyche.json"
    psyche_file.write_text(json.dumps({"mood": "focused"}))

    app = create_app(runs_dir=runs_dir, psyche_file=psyche_file)
    client = TestClient(app)

    response = client.get("/alerts")
    assert response.status_code == 200
    payload = response.json()
    assert payload["run"] == "loop"
    assert {item["kind"] for item in payload["alerts"]} == {
        "health_decline",
        "sandbox_failures_rising",
        "prolonged_stagnation",
    }




def test_dashboard_latest_run_summary_endpoint(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    (runs_dir / "older.jsonl").write_text(json.dumps({"event": "old"}) + "\n")
    latest = runs_dir / "latest.jsonl"
    latest.write_text(
        "\n".join(
            [
                json.dumps({"event": "start", "ts": "2026-04-12T10:00:00"}),
                json.dumps(
                    {
                        "ts": "2026-04-12T10:01:00",
                        "op": "flip",
                        "accepted": True,
                        "score_base": 10.0,
                        "score_new": 8.0,
                    }
                ),
                json.dumps(
                    {
                        "ts": "2026-04-12T10:02:00",
                        "operator": "swap",
                        "ok": False,
                        "score_base": 8.0,
                        "score_new": 9.0,
                    }
                ),
            ]
        )
        + "\n"
    )

    app = create_app(runs_dir=runs_dir, psyche_file=tmp_path / "psyche.json")
    summary = app._routes["/runs/latest/summary"]()
    assert summary["run"] == "latest"
    assert summary["summary"] == {
        "entries": 3,
        "mutations": 2,
        "accepted": 1,
        "rejected": 1,
        "last_event": "start",
        "last_timestamp": "2026-04-12T10:02:00",
    }

    latest_payload = app._routes["/runs/latest"]()
    assert latest_payload["run"] == "latest"
    assert len(latest_payload["records"]) == 3


def test_dashboard_cockpit_endpoint_schema(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    (runs_dir / "cockpit.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "ts": "2026-04-12T10:00:00",
                        "accepted": False,
                        "op": "flip",
                        "score_base": 10.0,
                        "score_new": 12.0,
                        "health": {"score": 85.0, "sandbox_stability": 0.85},
                    }
                ),
                json.dumps(
                    {
                        "ts": "2026-04-12T10:05:00",
                        "accepted": False,
                        "operator": "swap",
                        "score_base": 12.0,
                        "score_new": 14.0,
                        "health": {"score": 80.0, "sandbox_stability": 0.70},
                    }
                ),
            ]
        )
        + "\n"
    )

    app = create_app(runs_dir=runs_dir, psyche_file=tmp_path / "psyche.json")
    client = TestClient(app)

    response = client.get("/api/cockpit")
    assert response.status_code == 200
    payload = response.json()

    assert payload["run"] == "cockpit"
    assert payload["trend"] in {"amélioration", "plateau", "dégradation"}
    assert isinstance(payload["critical_alerts"], list)
    assert isinstance(payload["suggested_actions"], list)
    assert isinstance(payload["next_action"], str)
    assert payload["global_status"] in {"critical", "warning", "stable", "unknown"}
    assert "health_score" in payload
    assert "accepted_mutation_rate" in payload
    assert "last_notable_mutation" in payload


def test_dashboard_index_contains_cockpit_cards(tmp_path: Path) -> None:
    app = create_app(runs_dir=tmp_path / "runs", psyche_file=tmp_path / "psyche.json")
    client = TestClient(app)

    response = client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert "Cockpit" in body
    assert "Prochaine action recommandée" in body
    assert "/api/cockpit" in body
    assert "Frise des événements" in body
    assert "timeline-detail" in body


def test_dashboard_timeline_comparison_and_top_mutations(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    run_file = runs_dir / "mutations.jsonl"
    run_file.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "ts": "2026-04-10T10:00:00",
                        "skill": "life-a:skills/foo.py",
                        "op": "flip",
                        "accepted": True,
                        "score_base": 10.0,
                        "score_new": 7.0,
                        "ms_new": 40.0,
                        "health": {"score": 92.0},
                    }
                ),
                json.dumps(
                    {
                        "ts": "2026-04-10T12:00:00",
                        "skill": "life-a:skills/foo.py",
                        "op": "flip",
                        "accepted": False,
                        "score_base": 7.0,
                        "score_new": 8.0,
                        "ms_new": 60.0,
                        "health": {"score": 88.0},
                    }
                ),
                json.dumps(
                    {
                        "ts": "2026-04-11T09:00:00",
                        "skill": "life-b:skills/bar.py",
                        "op": "swap",
                        "accepted": True,
                        "score_base": 20.0,
                        "score_new": 16.0,
                        "ms_new": 30.0,
                        "health": {"score": 70.0},
                    }
                ),
            ]
        )
        + "\n"
    )
    psyche_file = tmp_path / "psyche.json"
    psyche_file.write_text(json.dumps({"mood": "focused"}))

    app = create_app(runs_dir=runs_dir, psyche_file=psyche_file)

    timeline_payload = app._routes["/timeline"](
        life="life-a",
        period="2026-04-10",
        operator="flip",
        decision="accepted",
        impact="beneficial",
    )
    assert timeline_payload["count"] == 1
    assert timeline_payload["filters"] == {
        "life": "life-a",
        "period": "2026-04-10",
        "operator": "flip",
        "decision": "accepted",
        "impact": "beneficial",
    }
    assert timeline_payload["items"][0]["life"] == "life-a"
    assert timeline_payload["items"][0]["impact"] == "beneficial"
    assert timeline_payload["items"][0]["impact_delta"] == 3.0

    comparison_payload = app._routes["/lives/comparison"]()["lives"]
    assert set(comparison_payload) == {"life-a", "life-b"}
    assert comparison_payload["life-a"]["health_score"] == 90.0
    assert comparison_payload["life-a"]["progression_slope"] == 2.0
    assert comparison_payload["life-a"]["failure_rate"] == 0.5
    assert comparison_payload["life-a"]["evolution_speed"] == 50.0
    assert comparison_payload["life-b"]["failure_rate"] == 0.0

    top_payload = app._routes["/mutations/top"](limit=1)
    assert set(top_payload) == {"most_beneficial", "most_risky", "most_frequent"}
    assert top_payload["most_beneficial"][0]["life"] == "life-b"
    assert top_payload["most_beneficial"][0]["impact_delta"] == 4.0
    assert top_payload["most_risky"][0]["life"] == "life-a"
    assert top_payload["most_risky"][0]["impact_delta"] == -1.0
    assert top_payload["most_frequent"][0] == {"operator": "flip", "count": 2}


def test_run_timeline_endpoint_filters_pagination_and_event_coherence(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    run_file = runs_dir / "run-42.jsonl"
    run_file.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "ts": "2026-04-10T08:00:00",
                        "skill": "orga:skills/a.py",
                        "op": "flip",
                        "accepted": True,
                        "score_base": 10.0,
                        "score_new": 8.5,
                        "human_summary": "mutation acceptée",
                        "decision_reason": "accepted: score improved",
                        "loop_modifications": {"for_changed": 1},
                        "diff": "@@ -1 +1 @@",
                    }
                ),
                json.dumps(
                    {
                        "ts": "2026-04-10T08:10:00",
                        "event": "delay",
                        "skill": "orga:skills/a.py",
                        "resume_at": 123.0,
                    }
                ),
                json.dumps(
                    {
                        "ts": "2026-04-10T08:20:00",
                        "event": "refuse",
                        "skill": "orga:skills/a.py",
                    }
                ),
                json.dumps(
                    {
                        "ts": "2026-04-10T08:30:00",
                        "event": "interaction",
                        "organism": "orga",
                        "interaction": "share",
                    }
                ),
                json.dumps(
                    {
                        "ts": "2026-04-11T09:00:00",
                        "event": "death",
                        "skill": "orgb:skills/b.py",
                        "reason": "resource exhaustion",
                    }
                ),
                json.dumps(
                    {
                        "ts": "2026-04-11T09:10:00",
                        "skill": "orgb:skills/b.py",
                        "operator": "swap",
                        "ok": False,
                        "score_base": 5.0,
                        "score_new": 6.0,
                        "human_summary": "mutation rejetée",
                        "decision_reason": "rejected: score regression",
                        "loop_modifications": {"while_changed": 2},
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    app = create_app(runs_dir=runs_dir, psyche_file=tmp_path / "psyche.json")
    route = app._routes["/api/runs/{run_id}/timeline"]

    all_payload = route(run_id="run-42", page=1, page_size=2)
    assert all_payload["pagination"] == {"page": 1, "page_size": 2, "total": 6, "total_pages": 3}
    assert [item["event"] for item in all_payload["items"]] == ["mutation", "delay"]

    page_two = route(run_id="run-42", page=2, page_size=2)
    assert [item["event"] for item in page_two["items"]] == ["refuse", "interaction"]

    filtered = route(
        run_id="run-42",
        operator="swap",
        decision="rejected",
        period_start="2026-04-11T00:00:00",
        period_end="2026-04-11T23:59:59",
        organism="orgb",
    )
    assert filtered["pagination"]["total"] == 1
    item = filtered["items"][0]
    assert item["event"] == "mutation"
    assert item["accepted"] is False
    assert item["human_summary"] == "mutation rejetée"
    assert item["decision_reason"] == "rejected: score regression"
    assert item["loop_modifications"] == {"while_changed": 2}
    assert item["score_before"] == 5.0
    assert item["score_after"] == 6.0

    event_types = {entry["event"] for entry in route(run_id="run-42")["items"]}
    assert {"mutation", "delay", "refuse", "death", "interaction"}.issubset(event_types)


def test_psyche_missing_returns_404(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()

    app = create_app(runs_dir=runs_dir, psyche_file=tmp_path / "psyche.json")
    client = TestClient(app)

    response = client.get("/psyche")
    assert response.status_code == 404


def test_websocket_stream_incremental_logs_and_growth_stability(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    log_file = runs_dir / "log.txt"
    log_file.write_text("first\n", encoding="utf-8")
    psyche_file = tmp_path / "psyche.json"
    psyche_file.write_text(json.dumps({"mood": "happy"}), encoding="utf-8")

    app = create_app(runs_dir=runs_dir, psyche_file=psyche_file)
    client = TestClient(app)

    with client.websocket_connect("/ws") as ws:
        first = _receive_with_timeout(ws)
        second = _receive_with_timeout(ws)
        received = {first["type"]: first["data"], second["type"]: second["data"]}
        assert received["psyche"] == {"mood": "happy"}
        assert received["logs"] == {"log.txt": ["first"]}

        with log_file.open("a", encoding="utf-8") as handle:
            handle.write("second\n")
        log_update = _receive_with_timeout(ws)
        assert log_update["type"] == "logs"
        assert log_update["data"] == {"log.txt": ["second"]}

        with log_file.open("a", encoding="utf-8") as handle:
            handle.write("third\n")
            handle.write("fourth\n")
        growth_update = _receive_with_timeout(ws)
        assert growth_update["type"] == "logs"
        assert growth_update["data"] == {"log.txt": ["third", "fourth"]}



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
