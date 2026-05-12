import json
from pathlib import Path
from queue import Empty

import pytest
from fastapi_stub import TestClient

import singular.dashboard as dashboard_module
from singular.dashboard import create_app, run
from singular.lives import LifeMetadata, create_life


def _receive_with_timeout(ws: TestClient._WSConnection, timeout: float = 2.0) -> dict[str, object]:
    try:
        return ws.ws._queue.get(timeout=timeout)
    except Empty as exc:  # pragma: no cover - defensive for slow CI
        raise AssertionError("timed out waiting for websocket message") from exc


def test_dashboard_endpoints(tmp_path: Path, monkeypatch) -> None:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    (runs_dir / "log.txt").write_text("hello")
    psyche_file = tmp_path / "psyche.json"
    data = {"mood": "happy"}
    psyche_file.write_text(json.dumps(data))

    monkeypatch.setenv("SINGULAR_HOME", str(tmp_path))
    app = create_app(runs_dir=runs_dir, psyche_file=psyche_file)
    client = TestClient(app)

    assert client.get("/logs").json() == {"log.txt": "hello"}
    assert client.get("/psyche").json() == data
    assert client.get("/alerts").json() == {"run": None, "alerts": []}
    context = client.get("/dashboard/context").json()
    assert context["policy"]["version"] == 1
    assert isinstance(context["policy_impact"], list)
    assert context["governance_policy"] == {
        "circuit_breaker_threshold": 3,
        "circuit_breaker_window_seconds": 180.0,
        "circuit_breaker_cooldown_seconds": 300.0,
        "safe_mode": False,
        "mutation_quota_per_window": 25,
    }
    assert "skills_lifecycle" in context
    assert "retention" in context
    retention = client.get("/api/retention/status").json()
    assert "usage" in retention
    assert "last_purge" in retention


def test_dashboard_context_normalizes_object_and_dict_life_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    object_life_dir = tmp_path / "object-life"
    dict_life_dir = tmp_path / "dict-life"
    object_life_dir.mkdir()
    dict_life_dir.mkdir()

    object_meta = LifeMetadata(
        name="Object Life",
        slug="object-life",
        path=object_life_dir,
        created_at="2026-05-12T08:00:00+00:00",
        status="active",
    )
    dict_meta = {
        "name": "Dict Life",
        "slug": "dict-life",
        "path": str(dict_life_dir),
        "created_at": "2026-05-12T09:00:00+00:00",
        "status": "extinct",
    }

    def fake_load_registry() -> dict[str, object]:
        return {
            "active": "object-life",
            "lives": {"object-life": object_meta, "dict-life": dict_meta},
        }

    monkeypatch.setattr(dashboard_module, "load_registry", fake_load_registry)
    monkeypatch.setenv("SINGULAR_HOME", str(tmp_path))

    app = create_app(psyche_file=tmp_path / "psyche.json")
    context = app._routes["/dashboard/context"]()

    assert context["registry_lives"] == [
        {
            "slug": "dict-life",
            "name": "Dict Life",
            "path": str(dict_life_dir),
            "status": "extinct",
            "active": False,
            "created_at": "2026-05-12T09:00:00+00:00",
        },
        {
            "slug": "object-life",
            "name": "Object Life",
            "path": str(object_life_dir),
            "status": "active",
            "active": True,
            "created_at": "2026-05-12T08:00:00+00:00",
        },
    ]


def test_dashboard_starts_with_empty_registry_and_exposes_onboarding(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "empty-root"
    root.mkdir()
    monkeypatch.setenv("SINGULAR_ROOT", str(root))
    monkeypatch.delenv("SINGULAR_HOME", raising=False)

    runs_dir = tmp_path / "runs"
    psyche_file = tmp_path / "psyche.json"
    psyche_file.write_text(json.dumps({"mood": "idle"}), encoding="utf-8")

    app = create_app(runs_dir=runs_dir, psyche_file=psyche_file)
    client = TestClient(app)

    index_response = client.get("/")
    assert index_response.status_code == 200

    context = client.get("/dashboard/context")
    assert context.status_code == 200
    context_payload = context.json()
    assert context_payload["registry_lives_count"] == 0
    assert context_payload["registry_state"] == {
        "active": None,
        "active_valid": False,
        "is_empty": True,
    }
    assert context_payload["onboarding"] == {
        "required": True,
        "message": "Aucune vie, créez-en une.",
    }

    comparison = client.get("/lives/comparison")
    assert comparison.status_code == 200
    comparison_payload = comparison.json()
    assert comparison_payload["table"] == []
    assert comparison_payload["onboarding"] == {
        "required": True,
        "message": "Aucune vie, créez-en une.",
    }


def test_lives_comparison_current_life_only_uses_registry_after_life_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry_root = tmp_path / "registry-root"
    registry_root.mkdir()
    monkeypatch.setenv("SINGULAR_ROOT", str(registry_root))
    monkeypatch.delenv("SINGULAR_HOME", raising=False)

    app = create_app()

    life = create_life("active-life")
    runs_dir = life.path / "runs"
    runs_dir.mkdir(parents=True)
    (runs_dir / "active-run.jsonl").write_text(
        json.dumps(
            {
                "ts": "2026-05-12T10:00:00+00:00",
                "life": life.slug,
                "accepted": True,
                "score_base": 10.0,
                "score_new": 8.0,
                "health": {"score": 91.0, "sandbox_stability": 0.98},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    # Equivalent to GET /lives/comparison?current_life_only=true; the test
    # FastAPI stub dispatches query parameters via direct route kwargs.
    payload = app._routes["/lives/comparison"](current_life_only=True)
    assert set(payload["lives"]) == {life.slug}
    assert payload["lives"][life.slug]["health_score"] == 91.0
    assert payload["table"][0]["life"] == life.slug


def test_dashboard_quests_endpoint(tmp_path: Path, monkeypatch) -> None:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    psyche_file = tmp_path / "psyche.json"
    psyche_file.write_text(json.dumps({"mood": "curious"}))

    mem_dir = tmp_path / "mem"
    mem_dir.mkdir()
    quests_state = {
        "active": [{"name": "q1", "status": "active", "started_at": "2026-01-01T00:00:00+00:00"}],
        "completed": [{"name": "q0", "status": "success", "started_at": "2026-01-01T00:00:00+00:00", "completed_at": "2026-01-01T00:01:00+00:00"}],
    }
    (mem_dir / "quests_state.json").write_text(json.dumps(quests_state), encoding="utf-8")

    monkeypatch.setenv("SINGULAR_HOME", str(tmp_path))
    app = create_app(runs_dir=runs_dir, psyche_file=psyche_file)
    client = TestClient(app)

    response = client.get("/quests")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["active"]) == 1
    assert len(payload["completed"]) == 1


def test_dashboard_work_items_schema_contains_required_fields(
    tmp_path: Path, monkeypatch
) -> None:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    psyche_file = tmp_path / "psyche.json"
    psyche_file.write_text(json.dumps({"mood": "curious"}), encoding="utf-8")

    mem_dir = tmp_path / "mem"
    mem_dir.mkdir()
    quests_state = {
        "active": [
            {
                "name": "q1",
                "status": "active",
                "updated_at": "2026-01-01T00:00:00+00:00",
                "next_step": "traiter alerte",
            }
        ],
        "completed": [],
    }
    (mem_dir / "quests_state.json").write_text(json.dumps(quests_state), encoding="utf-8")

    run_file = runs_dir / "loop.jsonl"
    run_file.write_text(json.dumps({"ts": "2026-01-01T00:00:00+00:00"}), encoding="utf-8")
    consciousness_file = runs_dir / "loop.consciousness.jsonl"
    consciousness_file.write_text(
        json.dumps(
            {
                "ts": "2026-01-01T00:01:00+00:00",
                "objective": "stabiliser",
                "success": True,
                "next_step": "ouvrir rapport",
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("SINGULAR_HOME", str(tmp_path))
    app = create_app(runs_dir=runs_dir, psyche_file=psyche_file)
    payload = TestClient(app).get("/api/dashboard/work-items").json()

    for section in ("objectives", "conversations"):
        assert "items" in payload[section]
        assert payload[section]["items"]
        for item in payload[section]["items"]:
            for required in ("title", "status", "last_update", "next_step"):
                assert required in item
                assert item[required]


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


def test_dashboard_includes_temporary_jsonl_run_files(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    run_file = runs_dir / "run-live-20260511090000.jsonl.tmp"
    run_file.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "ts": "2026-05-11T09:00:00+00:00",
                        "event": "interaction",
                        "organism": "temp-life",
                        "interaction": "signal",
                        "energy": 7,
                    }
                ),
                json.dumps(
                    {
                        "ts": "2026-05-11T09:01:00+00:00",
                        "skill": "temp-life:skills/adapt.py",
                        "operator": "swap",
                        "accepted": True,
                        "score_base": 10.0,
                        "score_new": 8.0,
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    app = create_app(runs_dir=runs_dir, psyche_file=tmp_path / "psyche.json")

    latest_payload = app._routes["/runs/latest"]()
    assert latest_payload["run"] == "run-live"
    assert [record["ts"] for record in latest_payload["records"]] == [
        "2026-05-11T09:00:00+00:00",
        "2026-05-11T09:01:00+00:00",
    ]

    timeline_payload = app._routes["/api/runs/{run_id}/timeline"](run_id="run-live")
    assert timeline_payload["pagination"]["total"] == 2
    assert [item["event"] for item in timeline_payload["items"]] == [
        "interaction",
        "mutation",
    ]

    ecosystem_payload = app._routes["/ecosystem"]()
    assert ecosystem_payload["organisms"]["temp-life"]["last_interaction"] == "signal"
    assert ecosystem_payload["organisms"]["temp-life"]["energy"] == 7


def test_dashboard_surfaces_sandbox_events_from_temporary_run(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    run_file = runs_dir / "run-live-20260511090000.jsonl.tmp"
    run_file.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "ts": "2026-05-11T09:00:00+00:00",
                        "event": "interaction",
                        "interaction": "sandbox_violation",
                        "organism": "temp-life",
                        "skill": "temp-life:skills/bad.py",
                        "severity": "critical",
                        "category": "sandbox_violation",
                    }
                ),
                json.dumps(
                    {
                        "ts": "2026-05-11T09:01:00+00:00",
                        "event": "governance.circuit_breaker_opened",
                        "category": "sandbox_violation",
                        "severity": "critical",
                        "threshold": 3,
                        "cooldown_seconds": 300.0,
                        "open_until": "2099-05-11T09:06:00+00:00",
                        "corrective_action": "halt mutations until cooldown",
                    }
                ),
                json.dumps(
                    {
                        "ts": "2026-05-11T09:02:00+00:00",
                        "event": "interaction",
                        "interaction": "mutation_halted",
                        "organism": "temp-life",
                        "target": "temp-life:skills/bad.py",
                        "severity": "critical",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    app = create_app(runs_dir=runs_dir, psyche_file=tmp_path / "psyche.json")

    cockpit_payload = app._routes["/api/cockpit"]()
    governance = cockpit_payload["sandbox_governance"]
    assert governance["circuit_breaker_status"] == "ouvert"
    assert governance["recent_violations_count"] == 2
    assert governance["last_faulty_skill"] == "temp-life:skills/bad.py"
    assert {item["event"] for item in governance["events"]} >= {
        "sandbox_violation",
        "governance.circuit_breaker_opened",
        "mutation_halted",
    }

    timeline_payload = app._routes["/api/runs/{run_id}/timeline"](run_id="run-live")
    assert [item["event"] for item in timeline_payload["items"]] == [
        "sandbox_violation",
        "governance.circuit_breaker_opened",
        "mutation_halted",
    ]

    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        assert [_receive_with_timeout(ws)["event"] for _ in range(3)] == [
            "sandbox_violation",
            "governance.circuit_breaker_opened",
            "mutation_halted",
        ]


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
    assert "vital_timeline" in payload
    assert "state" in payload["vital_timeline"]
    assert "autonomy_metrics" in payload
    assert "proactive_initiative_rate" in payload["autonomy_metrics"]
    assert "vital_metrics" in payload
    assert "circadian_cycle" in payload["vital_metrics"]
    assert "active_objectives" in payload["vital_metrics"]
    assert "energy_resources" in payload["vital_metrics"]
    assert "code_generation" in payload["vital_metrics"]
    assert "risks" in payload["vital_metrics"]
    assert "skills_lifecycle" in payload
    assert "trajectory" in payload
    assert "objectives" in payload["trajectory"]
    assert "priority_changes" in payload["trajectory"]
    assert "objective_narrative_links" in payload["trajectory"]


def test_dashboard_cockpit_sandbox_governance_summary(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    (runs_dir / "sandbox.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "ts": "2026-05-11T08:00:00+00:00",
                        "event": "interaction",
                        "interaction": "sandbox_violation",
                        "organism": "life-a",
                        "skill": "life-a:skills/bad.py",
                        "severity": "critical",
                    }
                ),
                json.dumps(
                    {
                        "ts": "2026-05-11T08:05:00+00:00",
                        "event": "governance.circuit_breaker_opened",
                        "category": "sandbox_violation",
                        "severity": "critical",
                        "cooldown_seconds": 300.0,
                        "open_until": "2099-05-11T08:10:00+00:00",
                        "corrective_action": "halt mutations until cooldown",
                    }
                ),
                json.dumps(
                    {
                        "ts": "2026-05-11T08:06:00+00:00",
                        "event": "skill.quarantined",
                        "skill": "life-a:skills/bad.py",
                        "disabled_until": "2099-05-11T09:00:00+00:00",
                        "reason": "consecutive_sandbox_failures",
                    }
                ),
                json.dumps(
                    {
                        "ts": "2026-05-11T08:07:00+00:00",
                        "event": "interaction",
                        "interaction": "mutation_halted",
                        "organism": "life-a",
                        "target": "life-a:skills/bad.py",
                        "severity": "critical",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    payload = TestClient(create_app(runs_dir=runs_dir, psyche_file=tmp_path / "psyche.json")).get(
        "/api/cockpit"
    ).json()

    assert payload["governance_policy"]["circuit_breaker_threshold"] == 3
    assert payload["governance_policy"]["circuit_breaker_window_seconds"] == 180.0
    assert payload["governance_policy"]["circuit_breaker_cooldown_seconds"] == 300.0
    assert payload["governance_policy"]["safe_mode"] is False
    assert payload["governance_policy"]["mutation_quota_per_window"] == 25

    governance = payload["sandbox_governance"]
    assert governance["circuit_breaker_status"] == "ouvert"
    assert governance["recent_violations_count"] == 2
    assert governance["last_faulty_skill"] == "life-a:skills/bad.py"
    assert governance["cooldown_remaining_seconds"] > 0
    assert governance["recommended_corrective_action"] == "halt mutations until cooldown"
    assert governance["empty_state"] is None
    assert {item["event"] for item in governance["events"]} >= {
        "sandbox_violation",
        "governance.circuit_breaker_opened",
        "skill.quarantined",
        "mutation_halted",
    }


def test_dashboard_cockpit_sandbox_governance_empty_state(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    (runs_dir / "empty-sandbox.jsonl").write_text(
        json.dumps({"ts": "2026-05-11T08:00:00+00:00", "health": {"score": 99.0}}) + "\n",
        encoding="utf-8",
    )

    payload = TestClient(create_app(runs_dir=runs_dir, psyche_file=tmp_path / "psyche.json")).get(
        "/api/cockpit"
    ).json()

    governance = payload["sandbox_governance"]
    assert governance["recent_violations_count"] == 0
    assert governance["empty_state"] == "aucune violation sandbox récente"


def test_dashboard_cockpit_essential_projection_schema(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    (runs_dir / "essential.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "ts": "2026-04-12T10:00:00",
                        "accepted": False,
                        "op": "flip",
                        "score_base": 10.0,
                        "score_new": 12.0,
                        "health": {"score": 70.0, "sandbox_stability": 0.6},
                    }
                ),
                json.dumps(
                    {
                        "ts": "2026-04-12T10:05:00",
                        "event": "alert",
                        "kind": "health_decline",
                        "severity": "critical",
                    }
                ),
            ]
        )
        + "\n"
    )

    app = create_app(runs_dir=runs_dir, psyche_file=tmp_path / "psyche.json")
    client = TestClient(app)
    response = client.get("/api/cockpit/essential")
    assert response.status_code == 200
    payload = response.json()

    assert payload == {
        "schema_version": "2026-04-15",
        "global_status": payload["global_status"],
        "critical_alerts_count": payload["critical_alerts_count"],
        "next_action": payload["next_action"],
        "selected_life": payload["selected_life"],
        "active_incidents_count": payload["active_incidents_count"],
    }
    assert payload["global_status"] in {"critical", "warning", "stable", "unknown"}
    assert isinstance(payload["critical_alerts_count"], int)
    assert isinstance(payload["next_action"], str)
    assert isinstance(payload["selected_life"], str)
    assert isinstance(payload["active_incidents_count"], int)


def test_dashboard_index_contains_cockpit_cards(tmp_path: Path) -> None:
    app = create_app(runs_dir=tmp_path / "runs", psyche_file=tmp_path / "psyche.json")
    client = TestClient(app)

    response = client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert "kpi-retention-usage" in body
    assert "kpi-retention-thresholds" in body
    assert "sandbox-governance-card" in body
    assert "aucune violation sandbox récente" in body
    assert "Action corrective recommandée" in body
    assert "Cockpit" in body
    assert "Prochaine action" in body
    assert "Métriques d’autonomie" in body
    assert "Taux d’initiatives proactives" in body
    assert "/api/cockpit" in body
    assert "Timeline des événements" in body
    assert "timeline-diff" in body
    assert "Voir détail" in body
    assert "Vies · Tableau comparatif" in body
    assert "Runs non rattachés" in body
    assert "data-sort='life'" in body
    assert "<td colspan='7'>Aucune vie ne correspond aux filtres.</td>" in body
    assert "lives-quick-filters" in body
    assert "filter-chip" in body
    assert "Logs en direct" in body
    assert "live-autoscroll" in body
    assert "live-toggle" in body
    assert "Qu’est-ce que ce score ?" in body
    assert "Pourquoi cette alerte ?" in body
    assert "Navigation" in body
    assert "#cockpit" in body
    assert "#timeline-section" in body
    assert "Timeline des réflexions" in body
    assert "reflection-objective" in body
    assert "#vies" in body
    assert "#logs-live" in body
    assert "#parametres" in body
    assert "Registre courant (SINGULAR_ROOT)" in body
    assert "Vie courante (SINGULAR_HOME)" in body
    assert "Nombre de vies détectées" in body
    assert "Quêtes" in body
    assert "quests-table-body" in body
    assert "objectives-table-body" in body
    assert "conversations-table-body" in body
    assert "Voir JSON" in body
    assert "Cycle circadien & objectifs actifs" in body
    assert "Trajectory des objectifs" in body
    assert "kpi-trajectory-in-progress" in body
    assert "kpi-priority-changes-list" in body
    assert "Cycle de vie des skills" in body
    assert "Énergie / ressources & génération de code" in body
    assert "Fenêtre temporelle" in body
    assert "Tri prédéfini" in body
    assert "À surveiller" in body
    assert "Plus actives" in body
    assert "Nouvelles" in body
    assert "filter-time-window" in body
    assert "life-detail-panel" in body
    assert "<th><button data-sort='life'>Nom</button></th>" in body
    assert "<th><button data-sort='score'>Score / santé</button></th>" in body
    assert "<th><button data-sort='last_activity'>Dernière activité</button></th>" in body
    assert "<th><button data-sort='liveness'>Liveness</button></th>" in body
    assert "<th>Statut</th>" in body
    assert "<th>Risques</th>" in body
    assert "essential-selected-life" in body
    assert "essential-active-incidents" in body
    assert "data-essential-level='1'" in body
    assert "data-essential-level='2'" in body
    assert "data-essential-level='3'" in body


def test_dashboard_essential_mode_critical_blocks_and_visibility_markers(tmp_path: Path) -> None:
    app = create_app(runs_dir=tmp_path / "runs", psyche_file=tmp_path / "psyche.json")
    body = TestClient(app).get("/").json()

    for marker in [
        "id='cockpit-status'",
        "id='kpi-alerts'",
        "id='kpi-next-action'",
        "id='essential-selected-life'",
        "id='essential-active-incidents'",
    ]:
        assert marker in body

    assert "id='cockpit-detail' class='panel level-panel technical-only' data-essential-level='3'" in body
    assert "class='lives-grid' data-essential-level='2'" in body
    assert "class='lives-grid technical-only'" not in body


def test_dashboard_index_renders_main_sections(tmp_path: Path) -> None:
    app = create_app(runs_dir=tmp_path / "runs", psyche_file=tmp_path / "psyche.json")
    body = TestClient(app).get("/").json()

    assert "<section id=\"cockpit\">" in body
    assert "<section id=\"timeline-section\">" in body
    assert "<section id=\"reflections-section\">" in body
    assert "<section id=\"vies\">" in body
    assert "<section id=\"logs-live\">" in body
    assert "<section id=\"parametres\">" in body


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
    assert comparison_payload["life-a"]["current_health_score"] == 88.0
    assert comparison_payload["life-a"]["trend"] == "dégradation"
    assert comparison_payload["life-a"]["iterations"] == 2
    assert comparison_payload["life-b"]["failure_rate"] == 0.0

    top_payload = app._routes["/mutations/top"](limit=1)
    assert set(top_payload) == {"most_beneficial", "most_risky", "most_frequent"}
    assert top_payload["most_beneficial"][0]["life"] == "life-b"
    assert top_payload["most_beneficial"][0]["impact_delta"] == 4.0
    assert top_payload["most_risky"][0]["life"] == "life-a"
    assert top_payload["most_risky"][0]["impact_delta"] == -1.0
    assert top_payload["most_frequent"][0] == {"operator": "flip", "count": 2}


def test_dashboard_consciousness_endpoint_filters(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    run_file = runs_dir / "mind-20260412101010.jsonl"
    run_file.write_text(json.dumps({"event": "start"}) + "\n", encoding="utf-8")

    run_dir = runs_dir / "mind"
    run_dir.mkdir()
    (run_dir / "consciousness.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "ts": "2026-04-12T10:10:10",
                        "objective": "coherence",
                        "success": True,
                        "emotional_state": {"mood": "focused"},
                    }
                ),
                json.dumps(
                    {
                        "ts": "2026-04-12T10:11:10",
                        "objective": "exploration",
                        "success": False,
                        "emotional_state": {"mood": "fatigue"},
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    app = create_app(runs_dir=runs_dir, psyche_file=tmp_path / "psyche.json")
    payload = app._routes["/api/runs/{run_id}/consciousness"](
        run_id="mind-20260412101010",
        objective="coherence",
        success="true",
        mood="focused",
    )

    assert payload["count"] == 1
    assert payload["items"][0]["objective"] == "coherence"


def test_dashboard_lives_comparison_excludes_runs_without_explicit_life(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    (runs_dir / "loop-1001.jsonl").write_text(
        json.dumps(
            {
                "ts": "2026-04-12T12:00:00",
                "op": "flip",
                "accepted": True,
                "score_base": 12.0,
                "score_new": 10.0,
                "health": {"score": 77.0},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (runs_dir / "with-life.jsonl").write_text(
        json.dumps(
            {
                "ts": "2026-04-12T12:05:00",
                "life": "life-explicit",
                "op": "swap",
                "accepted": True,
                "score_base": 10.0,
                "score_new": 8.0,
                "health": {"score": 91.0},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    app = create_app(runs_dir=runs_dir, psyche_file=tmp_path / "psyche.json")
    payload = app._routes["/lives/comparison"]()

    assert set(payload["lives"]) == {"life-explicit"}
    assert "loop-1001" not in payload["lives"]
    assert payload["unattached_runs"] == {
        "records_count": 1,
        "runs_count": 1,
        "runs": [{"run_id": "loop-1001", "records_count": 1}],
    }


def test_dashboard_code_evolution_endpoint_and_comparison_link(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    (runs_dir / "run-2001.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "ts": "2026-04-12T12:10:00Z",
                        "life": "life-explicit",
                        "file": "skills/perf.py",
                        "change_type": "perf_fix",
                        "score_base": 12.0,
                        "score_new": 9.0,
                        "ms_base": 110.0,
                        "ms_new": 88.0,
                        "accepted": True,
                        "trace_id": "trace-ok",
                    }
                ),
                json.dumps(
                    {
                        "ts": "2026-04-12T12:11:00Z",
                        "life": "life-explicit",
                        "module": "singular.life.loop",
                        "operator": "cleanup",
                        "score_base": 9.0,
                        "score_new": 10.0,
                        "ok": False,
                        "trace_id": "trace-ko",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    app = create_app(runs_dir=runs_dir, psyche_file=tmp_path / "psyche.json")
    client = TestClient(app)

    comparison_payload = client.get("/lives/comparison").json()
    life_row = next(row for row in comparison_payload["table"] if row["life"] == "life-explicit")
    assert life_row["code_evolution_endpoint"] == "/api/lives/life-explicit/code-evolution"

    endpoint_payload = app._routes["/api/lives/{life}/code-evolution"](life="life-explicit")
    assert endpoint_payload["life"] == "life-explicit"
    assert endpoint_payload["count"] == 2
    assert endpoint_payload["summary"]["by_status"] == {"accepté": 1, "rejeté": 1}
    assert endpoint_payload["items"][0]["run_id"] == "run-2001"

    filtered_payload = app._routes["/api/lives/{life}/code-evolution"](
        life="life-explicit",
        status="accepté",
        limit=1,
    )
    assert filtered_payload["count"] == 1
    assert filtered_payload["items"][0]["status"] == "accepté"


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
                        "ts": "2026-04-11T09:05:00",
                        "event": "governance.circuit_breaker_opened",
                        "category": "sandbox_violation",
                        "severity": "critical",
                        "threshold": 3,
                        "cooldown_seconds": 300.0,
                        "open_until": "2026-04-11T09:10:00+00:00",
                        "corrective_action": "halt mutations until cooldown",
                        "last_sandbox_diagnostics": {"sandbox_violation_streak": 3},
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
    assert all_payload["pagination"] == {"page": 1, "page_size": 2, "total": 7, "total_pages": 4}
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
    assert {
        "mutation",
        "delay",
        "refuse",
        "death",
        "interaction",
        "governance.circuit_breaker_opened",
    }.issubset(event_types)
    breaker_item = next(
        entry for entry in route(run_id="run-42")["items"]
        if entry["event"] == "governance.circuit_breaker_opened"
    )
    assert breaker_item["category"] == "sandbox_violation"
    assert breaker_item["severity"] == "critical"
    assert breaker_item["threshold"] == 3
    assert breaker_item["cooldown_seconds"] == 300.0
    assert breaker_item["open_until"] == "2026-04-11T09:10:00+00:00"
    assert breaker_item["last_sandbox_diagnostics"] == {"sandbox_violation_streak": 3}


def test_run_mutation_detail_endpoint_returns_diff_metrics_and_ast(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    run_file = runs_dir / "run-mut.jsonl"
    run_file.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "ts": "2026-04-12T09:00:00",
                        "skill": "orga:skills/a.py",
                        "op": "flip",
                        "accepted": True,
                        "score_base": 10.0,
                        "score_new": 8.0,
                        "ms_base": 120.0,
                        "ms_new": 95.0,
                        "health_base": 71.0,
                        "health_new": 78.0,
                        "human_summary": "La mutation simplifie la boucle.",
                        "diff": "@@ -1,3 +1,3 @@\n-def old():\n+def new():",
                        "lines_added": 1,
                        "lines_removed": 1,
                        "functions_modified": ["old", "new"],
                        "ast_before": {"type": "Module", "body": ["FunctionDef old"]},
                        "ast_after": {"type": "Module", "body": ["FunctionDef new"]},
                    }
                ),
                json.dumps(
                    {
                        "ts": "2026-04-12T09:05:00",
                        "skill": "orga:skills/a.py",
                        "op": "swap",
                        "ok": False,
                        "score_base": 8.0,
                        "score_new": 9.0,
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    app = create_app(runs_dir=runs_dir, psyche_file=tmp_path / "psyche.json")
    route = app._routes["/api/runs/{run_id}/mutations/{index}"]

    payload = route(run_id="run-mut", index=0)
    assert payload["run_id"] == "run-mut"
    assert payload["index"] == 0
    assert payload["diff"] == "@@ -1,3 +1,3 @@\n-def old():\n+def new():"
    assert payload["human_summary"] == "La mutation simplifie la boucle."
    assert payload["metrics"] == {
        "lines_added": 1,
        "lines_removed": 1,
        "functions_modified": ["old", "new"],
        "ast_before": {"type": "Module", "body": ["FunctionDef old"]},
        "ast_after": {"type": "Module", "body": ["FunctionDef new"]},
    }
    assert payload["impact"] == {
        "score_before": 10.0,
        "score_after": 8.0,
        "perf_ms_before": 120.0,
        "perf_ms_after": 95.0,
        "health_before": 71.0,
        "health_after": 78.0,
    }


def test_lives_comparison_table_aggregation_filters_and_sorting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    (runs_dir / "multi.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "ts": "2026-04-10T09:00:00",
                        "skill": "life-a:skills/a.py",
                        "accepted": False,
                        "score_base": 10.0,
                        "score_new": 11.0,
                        "health": {"score": 90.0, "sandbox_stability": 0.90},
                    }
                ),
                json.dumps(
                    {
                        "ts": "2026-04-10T10:00:00",
                        "skill": "life-a:skills/a.py",
                        "accepted": False,
                        "score_base": 11.0,
                        "score_new": 12.0,
                        "health": {"score": 87.0, "sandbox_stability": 0.80},
                    }
                ),
                json.dumps(
                    {
                        "ts": "2026-04-11T09:00:00",
                        "skill": "life-b:skills/b.py",
                        "accepted": True,
                        "score_base": 20.0,
                        "score_new": 16.0,
                        "health": {"score": 76.0, "sandbox_stability": 0.95},
                    }
                ),
                json.dumps(
                    {
                        "ts": "2026-04-11T10:00:00",
                        "event": "death",
                        "skill": "life-b:skills/b.py",
                    }
                ),
                json.dumps(
                    {
                        "ts": "2026-04-11T11:00:00",
                        "skill": "life-c:skills/c.py",
                        "accepted": True,
                        "score_base": 40.0,
                        "score_new": 35.0,
                        "health": {"score": 96.0, "sandbox_stability": 0.99},
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    app = create_app(runs_dir=runs_dir, psyche_file=tmp_path / "psyche.json")
    monkeypatch.setattr(
        "singular.dashboard.load_registry",
        lambda: {
            "active": "life-c",
            "lives": {
                "life-a": {"slug": "life-a", "name": "Life A"},
                "life-b": {"slug": "life-b", "name": "Life B", "status": "extinct"},
                "life-c": {"slug": "life-c", "name": "Life C", "status": "active"},
            },
        },
    )
    route = app._routes["/lives/comparison"]

    payload = route(sort_by="score", sort_order="desc")
    table = payload["table"]
    assert [row["life"] for row in table] == ["life-c", "life-a", "life-b"]
    assert payload["lives"]["life-a"]["trend"] == "dégradation"
    assert payload["lives"]["life-a"]["selected_life"] is False
    assert payload["lives"]["life-a"]["life_status"] == "active"
    assert payload["lives"]["life-a"]["is_registry_active_life"] is True
    assert payload["lives"]["life-a"]["extinction_seen_in_runs"] is False
    assert payload["lives"]["life-a"]["iterations"] == 2
    assert isinstance(payload["lives"]["life-a"]["alerts_count"], int)
    assert payload["lives"]["life-b"]["selected_life"] is False
    assert payload["lives"]["life-b"]["life_status"] == "extinct"
    assert payload["lives"]["life-b"]["is_registry_active_life"] is False
    assert payload["lives"]["life-b"]["extinction_seen_in_runs"] is True
    assert payload["lives"]["life-c"]["selected_life"] is True
    assert payload["lives"]["life-c"]["life_status"] == "active"
    assert payload["lives"]["life-c"]["stability"] == 0.99

    active_only = route(active_only=True)["table"]
    assert {row["life"] for row in active_only} == {"life-a", "life-c"}

    degrading_only = route(degrading_only=True)["table"]
    assert [row["life"] for row in degrading_only] == ["life-a"]

    dead_only = route(dead_only=True)["table"]
    assert [row["life"] for row in dead_only] == ["life-b"]

    by_life_asc = route(sort_by="life", sort_order="asc")["table"]
    assert [row["life"] for row in by_life_asc] == ["life-a", "life-b", "life-c"]


def test_lives_comparison_sorting_keeps_none_values_last(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    comparison = {
        "alpha": {
            "current_health_score": 10.0,
            "last_activity": "2026-04-10T10:00:00+00:00",
            "iterations": 2,
            "life_liveness_index": 60.0,
        },
        "bravo": {
            "current_health_score": None,
            "last_activity": None,
            "iterations": None,
            "life_liveness_index": None,
        },
        "charlie": {
            "current_health_score": 90.0,
            "last_activity": "2026-04-12T10:00:00+00:00",
            "iterations": 7,
            "life_liveness_index": 20.0,
        },
        "delta": {
            "current_health_score": 50.0,
            "last_activity": "2026-04-11T10:00:00+00:00",
            "iterations": 4,
            "life_liveness_index": 80.0,
        },
    }

    def fake_aggregate_lives_service(*args: object, **kwargs: object):
        return comparison, {"records_count": 0, "runs_count": 0, "runs": []}

    monkeypatch.setattr(
        dashboard_module, "aggregate_lives_service", fake_aggregate_lives_service
    )
    monkeypatch.setattr(
        dashboard_module,
        "load_registry",
        lambda: {"active": None, "lives": {}},
    )
    app = create_app(runs_dir=tmp_path / "runs", psyche_file=tmp_path / "psyche.json")
    route = app._routes["/lives/comparison"]

    expected = {
        ("score", "asc"): ["alpha", "delta", "charlie", "bravo"],
        ("score", "desc"): ["charlie", "delta", "alpha", "bravo"],
        ("last_activity", "asc"): ["alpha", "delta", "charlie", "bravo"],
        ("last_activity", "desc"): ["charlie", "delta", "alpha", "bravo"],
        ("iterations", "asc"): ["alpha", "delta", "charlie", "bravo"],
        ("iterations", "desc"): ["charlie", "delta", "alpha", "bravo"],
        ("liveness", "asc"): ["charlie", "alpha", "delta", "bravo"],
        ("liveness", "desc"): ["delta", "alpha", "charlie", "bravo"],
    }
    for (sort_by, sort_order), lives in expected.items():
        payload = route(sort_by=sort_by, sort_order=sort_order)
        assert [row["life"] for row in payload["table"]] == lives
        assert payload["table"][-1]["life"] == "bravo"


def test_lives_comparison_compare_lives_filter(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    (runs_dir / "compare.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "ts": "2026-04-11T09:00:00",
                        "skill": "life-a:skills/a.py",
                        "accepted": True,
                        "score_base": 10.0,
                        "score_new": 8.0,
                        "health": {"score": 80.0},
                    }
                ),
                json.dumps(
                    {
                        "ts": "2026-04-11T10:00:00",
                        "skill": "life-b:skills/b.py",
                        "accepted": True,
                        "score_base": 10.0,
                        "score_new": 7.5,
                        "health": {"score": 92.0},
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    app = create_app(runs_dir=runs_dir, psyche_file=tmp_path / "psyche.json")
    payload = app._routes["/lives/comparison"](compare_lives="life-a", time_window="all")
    assert set(payload["lives"]) == {"life-a"}
    assert payload["filters"]["compare_lives"] == ["life-a"]
    assert payload["filters"]["time_window"] == "all"


def test_lives_comparison_prefers_record_life_over_skill_prefix(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    (runs_dir / "compare.jsonl").write_text(
        json.dumps(
            {
                "ts": "2026-04-11T09:00:00",
                "life": "life-a",
                "skill": "loop-20260411090000:skills/a.py",
                "accepted": True,
                "score_base": 10.0,
                "score_new": 8.0,
                "health": {"score": 80.0},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    app = create_app(runs_dir=runs_dir, psyche_file=tmp_path / "psyche.json")

    payload = app._routes["/lives/comparison"]()

    assert set(payload["lives"]) == {"life-a"}


def test_lives_comparison_maps_timestamped_run_file_to_registry_life(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    (runs_dir / "loop-20260415120000.jsonl").write_text(
        json.dumps(
            {
                "ts": "2026-04-15T12:00:00",
                "accepted": True,
                "score_base": 12.0,
                "score_new": 9.0,
                "health": {"score": 88.0},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    app = create_app(runs_dir=runs_dir, psyche_file=tmp_path / "psyche.json")
    monkeypatch.setattr(
        "singular.dashboard.load_registry",
        lambda: {
            "active": "life-alpha",
            "lives": {"life-alpha": {"slug": "life-alpha", "run_id": "loop"}},
        },
    )

    payload = app._routes["/lives/comparison"]()

    assert "life-alpha" in payload["lives"]
    assert payload["unattached_runs"]["records_count"] == 0


def test_dashboard_life_metrics_contract_is_consistent_across_endpoints(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    (runs_dir / "contract.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "ts": "2026-04-10T09:00:00",
                        "skill": "life-a:skills/a.py",
                        "accepted": True,
                        "score_base": 9.0,
                        "score_new": 8.0,
                        "health": {"score": 80.0},
                    }
                ),
                json.dumps(
                    {
                        "ts": "2026-04-10T09:30:00",
                        "skill": "life-b:skills/b.py",
                        "event": "death",
                    }
                ),
                json.dumps(
                    {
                        "ts": "2026-04-10T10:00:00",
                        "skill": "life-c:skills/c.py",
                        "accepted": False,
                        "score_base": 10.0,
                        "score_new": 11.0,
                        "health": {"score": 70.0},
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    app = create_app(runs_dir=runs_dir, psyche_file=tmp_path / "psyche.json")
    monkeypatch.setattr(
        "singular.dashboard.load_registry",
        lambda: {
            "active": "life-c",
            "lives": {
                "life-a": {"slug": "life-a", "status": "active"},
                "life-b": {"slug": "life-b", "status": "extinct"},
                "life-c": {"slug": "life-c", "status": "active"},
            },
        },
    )

    cockpit_contract = app._routes["/api/cockpit"]()["life_metrics_contract"]
    comparison_contract = app._routes["/lives/comparison"]()["life_metrics_contract"]
    ecosystem_contract = app._routes["/ecosystem"]()["life_metrics_contract"]

    assert cockpit_contract["counts"] == {
        "total_lives": 3,
        "alive_lives": 2,
        "dead_lives": 1,
        "selected_lives": 1,
        "recent_activity_lives": 3,
    }
    assert comparison_contract == cockpit_contract
    assert ecosystem_contract == cockpit_contract


def test_lives_genealogy_returns_normalized_relationships_and_conflicts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "registry-root"
    (root / "mem").mkdir(parents=True)
    monkeypatch.setenv("SINGULAR_ROOT", str(root))
    monkeypatch.delenv("SINGULAR_HOME", raising=False)
    (root / "mem" / "lives_relations.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "ts": "2026-04-13T08:00:00+00:00",
                        "event": "ally",
                        "actor": "life-a",
                        "target": "life-b",
                        "details": {},
                    }
                ),
                json.dumps(
                    {
                        "ts": "2026-04-14T09:00:00+00:00",
                        "event": "rival",
                        "actor": "life-a",
                        "target": "life-c",
                        "details": {},
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    app = create_app(runs_dir=tmp_path / "runs", psyche_file=tmp_path / "psyche.json")
    monkeypatch.setattr(
        "singular.dashboard.load_registry",
        lambda: {
            "active": "life-a",
            "lives": {
                "life-a": {
                    "slug": "life-a",
                    "name": "Life A",
                    "status": "active",
                    "parents": [],
                    "children": ["life-b", "life-c"],
                    "allies": ["life-b"],
                    "rivals": ["life-c"],
                    "proximity_score": 0.82,
                    "lineage_depth": 0,
                },
                "life-b": {
                    "slug": "life-b",
                    "name": "Life B",
                    "status": "active",
                    "parents": ["life-a"],
                    "children": [],
                    "allies": ["life-a"],
                    "rivals": [],
                    "proximity_score": 0.66,
                    "lineage_depth": 1,
                },
                "life-c": {
                    "slug": "life-c",
                    "name": "Life C",
                    "status": "active",
                    "parents": ["life-a"],
                    "children": [],
                    "allies": [],
                    "rivals": ["life-a"],
                    "proximity_score": 0.3,
                    "lineage_depth": 1,
                },
            },
        },
    )

    payload = app._routes["/lives/genealogy"]()

    assert payload["filters"] == {"life": None}
    assert payload["active_relations"]
    for relation in payload["relationships"]:
        assert "type" in relation
        assert "status" in relation
        assert "updated_at" in relation
        assert "severity" in relation
    for conflict in payload["active_conflicts"]:
        assert "type" in conflict
        assert "status" in conflict
        assert "updated_at" in conflict
        assert "severity" in conflict
    first = payload["active_relations"][0]
    assert first["type"] == "rivalry"
    assert first["severity"] >= payload["active_relations"][-1]["severity"]


def test_lives_genealogy_life_filter_limits_active_relations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "registry-root"
    (root / "mem").mkdir(parents=True)
    monkeypatch.setenv("SINGULAR_ROOT", str(root))
    monkeypatch.delenv("SINGULAR_HOME", raising=False)
    app = create_app(runs_dir=tmp_path / "runs", psyche_file=tmp_path / "psyche.json")
    monkeypatch.setattr(
        "singular.dashboard.load_registry",
        lambda: {
            "active": "life-a",
            "lives": {
                "life-a": {"slug": "life-a", "allies": ["life-b"], "rivals": ["life-c"]},
                "life-b": {"slug": "life-b", "allies": ["life-a"], "rivals": []},
                "life-c": {"slug": "life-c", "allies": [], "rivals": ["life-a"]},
            },
        },
    )

    payload = app._routes["/lives/genealogy"](life="life-b")

    assert payload["filters"] == {"life": "life-b"}
    assert payload["active_relations"]
    assert all(
        relation["source"] == "life-b" or relation["target"] == "life-b"
        for relation in payload["active_relations"]
    )


def test_psyche_missing_returns_404(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()

    app = create_app(runs_dir=runs_dir, psyche_file=tmp_path / "psyche.json")
    client = TestClient(app)

    response = client.get("/psyche")
    assert response.status_code == 404


def test_websocket_stream_incremental_events_and_growth_stability(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    run_file = runs_dir / "run-live-20260511090000.jsonl.tmp"
    run_file.write_text(
        json.dumps({"ts": "2026-04-12T10:00:00", "event": "interaction"}) + "\n",
        encoding="utf-8",
    )
    psyche_file = tmp_path / "psyche.json"
    psyche_file.write_text(json.dumps({"mood": "happy"}), encoding="utf-8")

    app = create_app(runs_dir=runs_dir, psyche_file=psyche_file)
    client = TestClient(app)

    with client.websocket_connect("/ws") as ws:
        first = _receive_with_timeout(ws)
        second = _receive_with_timeout(ws)
        assert first == {"type": "psyche", "data": {"mood": "happy"}} or second == {
            "type": "psyche",
            "data": {"mood": "happy"},
        }
        first_event = first if "run_id" in first else second
        assert first_event == {
            "type": "run_event",
            "run_id": "run-live",
            "event": "interaction",
            "ts": "2026-04-12T10:00:00",
        }

        with run_file.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"ts": "2026-04-12T10:00:01", "event": "delay"}) + "\n")
        update = _receive_with_timeout(ws)
        assert update == {
            "type": "run_event",
            "run_id": "run-live",
            "event": "delay",
            "ts": "2026-04-12T10:00:01",
        }

        with run_file.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"ts": "2026-04-12T10:00:02", "event": "refuse"}) + "\n")
            handle.write(
                json.dumps(
                    {
                        "ts": "2026-04-12T10:00:03",
                        "score_base": 10.0,
                        "score_new": 9.0,
                        "accepted": True,
                    }
                )
                + "\n"
            )
        growth_first = _receive_with_timeout(ws)
        growth_second = _receive_with_timeout(ws)
        assert [growth_first, growth_second] == [
            {
                "type": "run_event",
                "run_id": "run-live",
                "event": "refuse",
                "ts": "2026-04-12T10:00:02",
            },
            {
                "type": "run_event",
                "run_id": "run-live",
                "event": "mutation",
                "ts": "2026-04-12T10:00:03",
            },
        ]



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


def test_dashboard_actions_endpoint_and_ui_panel(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SINGULAR_DASHBOARD_ACTION_TOKEN", "secret")
    app = create_app(runs_dir=tmp_path / "runs", psyche_file=tmp_path / "psyche.json")
    client = TestClient(app)

    body = client.get("/").json()
    assert "Actions rapides" in body
    assert "action-result" in body
    assert "critical-action-result" in body
    assert "critical-birth" in body
    assert "data-dashboard-action='birth'" in body
    assert "critical-talk" in body
    assert "data-dashboard-action='talk'" in body
    assert "critical-archive" in body
    assert "data-dashboard-action='archive'" in body
    assert "critical-emergency-stop" in body
    assert "data-dashboard-action='emergency_stop'" in body
    assert "Créer vie" in body
    assert "Discuter" in body
    assert "Archiver" in body
    assert "Mémorial" in body
    assert "Cloner" in body

    ok = client.post("/api/actions/lives_list?token=secret", json={}).json()
    assert ok["ok"] is True
    assert ok["action"] == "lives_list"
    assert "context" in ok
    assert "registry_root" in ok["context"]
    assert "current_life_home" in ok["context"]

    with pytest.raises(Exception):
        app._routes["/api/actions/{action}"]("lives_list", token="wrong", payload="{}")


def test_dashboard_emergency_stop_action_writes_active_life_stop_signal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    monkeypatch.setenv("SINGULAR_ROOT", str(root))
    monkeypatch.delenv("SINGULAR_HOME", raising=False)
    meta = create_life("Urgence")

    app = create_app(
        runs_dir=meta.path / "runs", psyche_file=meta.path / "mem" / "psyche.json"
    )
    route = app._routes["/api/actions/{action}"]

    with pytest.raises(Exception):
        route("emergency_stop", payload=json.dumps({"scope": "active_life"}))

    result = TestClient(app).post(
        "/api/actions/emergency_stop", json={"scope": "active_life"}
    ).json()

    assert result["ok"] is True
    assert result["action"] == "emergency_stop"
    stop_path = meta.path / "mem" / "orchestrator.stop.json"
    assert result["data"]["stop_signal_path"] == str(stop_path)
    payload = json.loads(stop_path.read_text(encoding="utf-8"))
    assert payload["stop"] is True
    assert payload["reason"] == "dashboard_emergency_stop"
    assert payload["requested_by"] == "dashboard"
    assert payload["life"] == meta.slug

def test_dashboard_actions_validation_robustness(tmp_path: Path) -> None:
    app = create_app(runs_dir=tmp_path / "runs", psyche_file=tmp_path / "psyche.json")

    route = app._routes["/api/actions/{action}"]

    with pytest.raises(Exception):
        route("unknown", payload="{}")

    with pytest.raises(Exception):
        route("lives_list", payload="[]")

    with pytest.raises(Exception):
        route("talk", payload=json.dumps({"prompt": "   "}))

    with pytest.raises(Exception):
        route("loop", payload=json.dumps({"budget_seconds": -1}))

    with pytest.raises(Exception):
        route("lives_use", payload=json.dumps({"name": ""}))


def test_dashboard_registry_scope_aggregates_multiple_lives_and_can_filter_current_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root_default = tmp_path / "default-root"
    root_lab = tmp_path / "lab-root"
    default_alpha = root_default / "lives" / "alpha"
    default_beta = root_default / "lives" / "beta"
    lab_gamma = root_lab / "lives" / "gamma"
    (root_default / "lives").mkdir(parents=True)
    (root_lab / "lives").mkdir(parents=True)
    (default_alpha / "runs").mkdir(parents=True)
    (default_beta / "runs").mkdir(parents=True)
    (lab_gamma / "runs").mkdir(parents=True)

    (default_alpha / "runs" / "run-a.jsonl").write_text(
        json.dumps(
            {
                "ts": "2026-04-12T08:00:00",
                "life": "alpha",
                "op": "flip",
                "accepted": True,
                "score_base": 10.0,
                "score_new": 8.0,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (default_beta / "runs" / "run-b.jsonl").write_text(
        json.dumps(
            {
                "ts": "2026-04-12T09:00:00",
                "life": "beta",
                "op": "swap",
                "accepted": False,
                "score_base": 9.0,
                "score_new": 10.0,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (lab_gamma / "runs" / "run-c.jsonl").write_text(
        json.dumps(
            {
                "ts": "2026-04-12T10:00:00",
                "life": "gamma",
                "op": "noop",
                "accepted": True,
                "score_base": 6.0,
                "score_new": 5.0,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (root_default / "lives" / "registry.json").write_text(
        json.dumps(
            {
                "active": "alpha",
                "lives": {
                    "alpha": {
                        "name": "Alpha",
                        "slug": "alpha",
                        "path": str(default_alpha),
                        "created_at": "2026-04-12T00:00:00+00:00",
                        "status": "active",
                    },
                    "beta": {
                        "name": "Beta",
                        "slug": "beta",
                        "path": str(default_beta),
                        "created_at": "2026-04-12T00:05:00+00:00",
                        "status": "active",
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    (root_lab / "lives" / "registry.json").write_text(
        json.dumps(
            {
                "active": "gamma",
                "lives": {
                    "gamma": {
                        "name": "Gamma",
                        "slug": "gamma",
                        "path": str(lab_gamma),
                        "created_at": "2026-04-12T00:10:00+00:00",
                        "status": "active",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("SINGULAR_ROOT", str(root_default))
    monkeypatch.setenv("SINGULAR_HOME", str(default_alpha))

    app = create_app(psyche_file=tmp_path / "psyche.json")
    context = app._routes["/dashboard/context"]()
    assert context["singular_root"] == str(root_default)
    assert context["singular_home"] == str(default_alpha)
    assert context["registry_lives_count"] == 2

    timeline_all = app._routes["/timeline"]()
    assert timeline_all["count"] == 2
    assert {item["life"] for item in timeline_all["items"]} == {"alpha", "beta"}

    timeline_current = app._routes["/timeline"](current_life_only=True)
    assert timeline_current["count"] == 1
    assert timeline_current["items"][0]["life"] == "alpha"


def test_lives_comparison_get_does_not_reconcile_registry_silently(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SINGULAR_ROOT", str(tmp_path))
    monkeypatch.delenv("SINGULAR_HOME", raising=False)

    registry_dir = tmp_path / "lives"
    registry_dir.mkdir(parents=True)
    registry_file = registry_dir / "registry.json"
    registry_payload = {
        "active": "alpha",
        "lives": {
            "alpha": {
                "name": "alpha",
                "slug": "alpha",
                "path": str(tmp_path / "alpha"),
                "created_at": "2026-05-12T00:00:00+00:00",
                "status": "active",
            }
        },
    }
    registry_file.write_text(json.dumps(registry_payload, indent=2), encoding="utf-8")

    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    (runs_dir / "run-death.jsonl").write_text(
        json.dumps(
            {
                "life": "alpha",
                "ts": "2026-05-12T01:00:00+00:00",
                "event": "death",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    app = create_app(runs_dir=runs_dir, psyche_file=tmp_path / "psyche.json")
    client = TestClient(app)

    before = registry_file.read_text(encoding="utf-8")
    first_payload = client.get("/lives/comparison").json()
    between = registry_file.read_text(encoding="utf-8")
    second_payload = client.get("/lives/comparison").json()
    after = registry_file.read_text(encoding="utf-8")

    assert before == between == after
    assert json.loads(after)["lives"]["alpha"]["status"] == "active"
    assert first_payload["lives"]["alpha"]["life_status"] == "active"
    assert first_payload["lives"]["alpha"]["extinction_seen_in_runs"] is True
    assert first_payload["lives"]["alpha"]["registry_run_status_inconsistency"] is True
    assert first_payload["lives"]["alpha"]["status_reconciliation_suggestion"] == "mark_extinct"
    assert first_payload["status_reconciliation"] == second_payload["status_reconciliation"] == [
        {
            "life": "alpha",
            "registry_status": "active",
            "extinction_seen_in_runs": True,
            "suggestion": "mark_extinct",
        }
    ]


def test_lives_status_reconciliation_action_marks_suggested_extinctions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SINGULAR_ROOT", str(tmp_path))
    monkeypatch.delenv("SINGULAR_HOME", raising=False)

    registry_dir = tmp_path / "lives"
    registry_dir.mkdir(parents=True)
    registry_file = registry_dir / "registry.json"
    registry_file.write_text(
        json.dumps(
            {
                "active": "alpha",
                "lives": {
                    "alpha": {
                        "name": "alpha",
                        "slug": "alpha",
                        "path": str(tmp_path / "alpha"),
                        "created_at": "2026-05-12T00:00:00+00:00",
                        "status": "active",
                    }
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    (runs_dir / "run-death.jsonl").write_text(
        json.dumps(
            {
                "life": "alpha",
                "ts": "2026-05-12T01:00:00+00:00",
                "event": "death",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    app = create_app(runs_dir=runs_dir, psyche_file=tmp_path / "psyche.json")
    client = TestClient(app)

    response = client.post("/api/lives/reconcile-status")

    assert response.status_code == 200
    assert response.json()["applied"] == [
        {
            "life": "alpha",
            "slug": "alpha",
            "from_status": "active",
            "to_status": "extinct",
            "suggestion": "mark_extinct",
        }
    ]
    assert json.loads(registry_file.read_text(encoding="utf-8"))["lives"]["alpha"]["status"] == "extinct"
