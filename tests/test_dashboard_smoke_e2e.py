from __future__ import annotations

import json
import inspect
import os
from pathlib import Path
import socket
import threading
import time

import pytest
from fastapi.testclient import TestClient

from singular.dashboard import create_app
from singular.lives import LifeMetadata


def _route(app: object, path: str, *, method: str = "GET"):
    """Return a route endpoint from either FastAPI or the unit-test stub."""
    stub_routes = getattr(
        app, "_ws_routes" if method == "WEBSOCKET" else "_routes", None
    )
    if stub_routes is not None:
        return stub_routes[path]
    for route in app.routes:
        if route.path == path and (
            method == "WEBSOCKET" or method in getattr(route, "methods", ())
        ):
            endpoint = route.endpoint

            def call_endpoint(*args, **kwargs):
                signature = inspect.signature(endpoint)
                bound = signature.bind_partial(*args, **kwargs)
                for name, parameter in signature.parameters.items():
                    default = parameter.default
                    if name not in bound.arguments and type(
                        default
                    ).__module__.startswith("fastapi."):
                        bound.arguments[name] = default.default
                return endpoint(*bound.args, **bound.kwargs)

            return call_endpoint
    raise LookupError(f"{method} route {path!r} is not registered")


@pytest.fixture
def dashboard_browser_url(tmp_path: Path) -> str:
    """Serve a real dashboard while a browser drives the public ``/`` route."""
    uvicorn = pytest.importorskip("uvicorn")
    app = create_app(runs_dir=tmp_path / "runs", psyche_file=tmp_path / "psyche.json")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]

    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 5
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert server.started, "the dashboard server did not become ready"
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=5)


def test_dashboard_browser_remains_responsive_when_backends_fail(
    dashboard_browser_url: str,
) -> None:
    """Bound post-bootstrap work and exercise every critical local control."""
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as driver:
        try:
            browser = driver.chromium.launch(headless=True)
        except playwright.Error as error:
            pytest.skip(f"Playwright Chromium is not installed: {error}")

        page = browser.new_page()
        page.add_init_script("""
            window.__dashboardProbe = {mutations: 0, scheduled: 0, network: 0};
            const NativeObserver = window.MutationObserver;
            window.MutationObserver = class extends NativeObserver {
              constructor(callback) {
                super((records, observer) => {
                  window.__dashboardProbe.mutations += records.length;
                  callback(records, observer);
                });
              }
            };
            for (const timerName of ['setTimeout', 'setInterval']) {
              const nativeTimer = window[timerName].bind(window);
              window[timerName] = (...args) => {
                window.__dashboardProbe.scheduled += 1;
                return nativeTimer(...args);
              };
            }
            const nativeFetch = window.fetch.bind(window);
            window.fetch = (...args) => {
              window.__dashboardProbe.network += 1;
              return nativeFetch(...args);
            };
            window.WebSocket = class UnavailableWebSocket {
              constructor() {
                queueMicrotask(() => this.onerror?.(new Event('error')));
              }
            };
            window.confirm = () => true;
            """)
        page.route(
            "**/api/cockpit*",
            lambda route: route.fulfill(
                status=503, content_type="application/json", body='{"detail":"offline"}'
            ),
        )
        page.route(
            "**/api/actions/birth",
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body='{"status":"created","name":"Browser Probe"}',
            ),
        )
        try:
            page.goto(
                dashboard_browser_url + "/", wait_until="networkidle", timeout=10_000
            )
            page.wait_for_selector("#updates-toggle", timeout=5_000)
            page.wait_for_function(
                "document.querySelector('#live-status')?.textContent.includes('indisponible')",
                timeout=2_000,
            )
            page.wait_for_function(
                "document.querySelector('#last-update-cockpit')?.textContent.includes('erreur')",
                timeout=5_000,
            )

            for tab in page.locator(".tab-trigger").all():
                tab.click()
                panel_id = tab.get_attribute("aria-controls")
                page.wait_for_function(
                    "id => !document.getElementById(id).classList.contains('panel-hidden')",
                    arg=panel_id,
                    timeout=1_000,
                )
                assert tab.get_attribute("aria-selected") == "true"

            essential = page.locator("#toggle-essential")
            essential.click()
            page.wait_for_function(
                "document.body.classList.contains('essential-mode')", timeout=1_000
            )
            assert essential.get_attribute("aria-pressed") == "true"

            # Return to the default pane and leave essential mode so the
            # expansion control is genuinely clickable, rather than invoking
            # a handler on a hidden element.
            page.locator("#tab-btn-decider").click()
            essential.click()
            expand = page.locator("[data-expand-target='cockpit-detail-json']")
            target_id = expand.get_attribute("data-expand-target")
            expand.click()
            page.wait_for_function(
                "id => !document.getElementById(id).classList.contains('panel-hidden')",
                arg=target_id,
                timeout=1_000,
            )
            assert expand.get_attribute("aria-expanded") == "true"

            page.locator("#updates-toggle").click()
            page.wait_for_function(
                "document.querySelector('#updates-status')?.textContent.includes('pause')",
                timeout=1_000,
            )
            page.locator("#operator-birth-name").fill("Browser Probe")
            page.locator("#critical-birth").click()
            page.wait_for_function(
                "document.querySelector('#critical-action-result')?.textContent !== "
                "'Aucune action critique exécutée.'",
                timeout=2_000,
            )

            # Once globally paused, neither observers, newly scheduled work, nor
            # requests may form a self-sustaining growth loop.
            page.wait_for_timeout(500)
            before = page.evaluate("({...window.__dashboardProbe})")
            page.wait_for_timeout(1_200)
            after = page.evaluate("({...window.__dashboardProbe})")
            assert after["network"] - before["network"] == 0
            assert after["scheduled"] - before["scheduled"] <= 2
            assert after["mutations"] - before["mutations"] <= 2

            started = time.monotonic()
            page.wait_for_function(
                "() => new Promise(resolve => setTimeout(() => resolve(true), 0))",
                timeout=1_000,
            )
            assert time.monotonic() - started < 1
        finally:
            browser.close()


def test_smoke_dashboard_e2e_capacites_critiques(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "registry-root"
    (root / "mem").mkdir(parents=True)

    home = tmp_path / "home"
    runs_dir = home / "runs"
    runs_dir.mkdir(parents=True)
    (home / "mem").mkdir(parents=True)

    run_id = "smoke"
    (runs_dir / f"{run_id}.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "ts": "2026-04-15T10:00:00+00:00",
                        "life": "life-a",
                        "operator": "flip",
                        "accepted": True,
                        "score_base": 10.0,
                        "score_new": 8.5,
                        "health": {"score": 82.0, "sandbox_stability": 0.9},
                    }
                ),
                json.dumps(
                    {
                        "ts": "2026-04-15T10:02:00+00:00",
                        "life": "life-a",
                        "event": "interaction",
                        "interaction": "resource.share",
                        "organism": "org-a",
                        "accepted": True,
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    consciousness_dir = runs_dir / run_id
    consciousness_dir.mkdir(parents=True)
    (consciousness_dir / "consciousness.jsonl").write_text(
        json.dumps(
            {
                "ts": "2026-04-15T10:03:00+00:00",
                "objective": "répondre au guidage humain",
                "summary": "dialogue opérateur",
                "success": True,
                "next_step": "publier synthèse",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    os.utime(
        runs_dir / f"{run_id}.jsonl",
        ns=(1_900_000_000_000_000_000, 1_900_000_000_000_000_000),
    )

    (home / "mem" / "quests_state.json").write_text(
        json.dumps(
            {
                "active": [
                    {
                        "name": "quest-critical",
                        "status": "active",
                        "started_at": "2026-04-15T09:00:00+00:00",
                        "next_step": "valider cockpit",
                    }
                ],
                "completed": [
                    {
                        "name": "quest-bootstrap",
                        "status": "success",
                        "started_at": "2026-04-15T08:00:00+00:00",
                        "completed_at": "2026-04-15T08:30:00+00:00",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    psyche_file = home / "mem" / "psyche.json"
    psyche_file.write_text(json.dumps({"mood": "focused"}), encoding="utf-8")

    monkeypatch.setenv("SINGULAR_ROOT", str(root))
    monkeypatch.setenv("SINGULAR_HOME", str(home))

    app = create_app(runs_dir=runs_dir, psyche_file=psyche_file)
    monkeypatch.setattr(
        "singular.dashboard.load_registry",
        lambda: {
            "active": "life-a",
            "lives": {
                "life-a": LifeMetadata(
                    name="Life A",
                    slug="life-a",
                    path=home,
                    created_at="2026-04-15T08:00:00+00:00",
                    status="active",
                    parents=(),
                    children=("life-b",),
                    allies=("life-b",),
                    rivals=(),
                    proximity_score=0.7,
                    lineage_depth=0,
                ),
                "life-b": LifeMetadata(
                    name="Life B",
                    slug="life-b",
                    path=home,
                    created_at="2026-04-15T08:05:00+00:00",
                    status="active",
                    parents=("life-a",),
                    children=(),
                    allies=("life-a",),
                    rivals=("life-a",),
                    proximity_score=0.45,
                    lineage_depth=1,
                ),
            },
        },
    )

    client = TestClient(app)

    context = client.get("/dashboard/context")
    assert context.status_code == 200
    context_payload = context.json()
    assert context_payload["registry_lives_count"] == 2
    assert context_payload["registry_state"]["active_valid"] is True

    comparison = client.get("/lives/comparison")
    assert comparison.status_code == 200
    comparison_payload = comparison.json()
    assert comparison_payload["table"]
    assert comparison_payload["life_metrics_contract"]["counts"]["total_lives"] >= 2

    cockpit = client.get("/api/cockpit")
    assert cockpit.status_code == 200
    cockpit_payload = cockpit.json()
    assert str(cockpit_payload["run"]).startswith(run_id)
    assert "accepted_mutation_rate" in cockpit_payload
    assert cockpit_payload["life_status"] in {
        "running",
        "budget_exhausted",
        "degraded",
        "mutation_paused",
        "terminal",
        "dead",
    }
    assert isinstance(cockpit_payload["life_status_score"], float)
    assert isinstance(cockpit_payload["life_status_explanation"], str)

    genealogy = client.get("/lives/genealogy")
    assert genealogy.status_code == 200
    genealogy_payload = genealogy.json()
    social_kinds = {edge["kind"] for edge in genealogy_payload["social_edges"]}
    assert "ally" in social_kinds
    assert "rival" in social_kinds

    quests = client.get("/quests")
    assert quests.status_code == 200
    quests_payload = quests.json()
    assert len(quests_payload["active"]) == 1

    timeline_payload = _route(app, "/api/runs/{run_id}/timeline")(run_id=run_id)
    assert any(item["event"] == "interaction" for item in timeline_payload["items"])

    work_items = client.get("/api/dashboard/work-items")
    assert work_items.status_code == 200
    work_items_payload = work_items.json()
    assert work_items_payload["conversations"]["items"]
    assert work_items_payload["conversations"]["items"][0]["title"]

    essential = client.get("/api/cockpit/essential")
    assert essential.status_code == 200
    essential_payload = essential.json()
    assert essential_payload["schema_version"] == "2026-04-15"
    assert "global_status" in essential_payload
    assert essential_payload["life_status"] == cockpit_payload["life_status"]
    assert (
        essential_payload["life_status_score"] == cockpit_payload["life_status_score"]
    )
    assert "life_status_summary" in essential_payload


@pytest.fixture
def active_run_dashboard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[TestClient, dict[str, Path]]:
    root = tmp_path / "registry-root"
    root.mkdir(parents=True)
    life_a = tmp_path / "life-a"
    life_b = tmp_path / "life-b"
    for life in (life_a, life_b):
        (life / "runs").mkdir(parents=True)
        (life / "mem").mkdir(parents=True)

    active_run = life_a / "runs" / "active-smoke.jsonl.tmp"
    active_run.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "ts": "2026-05-11T09:00:00+00:00",
                        "run_id": "active-smoke",
                        "life": "life-a",
                        "event": "mutation",
                        "operator": "flip",
                        "accepted": True,
                        "score_base": 12.0,
                        "score_new": 10.0,
                        "health": {"score": 84.0, "sandbox_stability": 0.95},
                        "objective": "stabiliser le cockpit",
                        "objective_status": "in_progress",
                        "objective_priority": "high",
                        "duration_seconds": 1.5,
                        "latency_ms": 120,
                        "memory": "mutation acceptée et mémorisée",
                    }
                ),
                json.dumps(
                    {
                        "ts": "2026-05-11T09:01:00+00:00",
                        "run_id": "active-smoke",
                        "life": "life-a",
                        "event": "interaction",
                        "interaction": "resource.share",
                        "organism": "org-active",
                        "energy": 8,
                        "resources": 5,
                        "score": 91,
                        "alive": True,
                        "accepted": True,
                        "duration_seconds": 0.5,
                        "latency_ms": 80,
                    }
                ),
                json.dumps(
                    {
                        "ts": "2026-05-11T09:02:00+00:00",
                        "run_id": "active-smoke",
                        "life": "life-a",
                        "event": "orchestrator.decision",
                        "decision": "continue",
                        "reason": "health stable and resources available",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    os.utime(active_run, ns=(1_900_100_000_000_000_000, 1_900_100_000_000_000_000))

    (life_b / "runs" / "background.jsonl").write_text(
        json.dumps(
            {
                "ts": "2026-05-11T08:30:00+00:00",
                "run_id": "background",
                "life": "life-b",
                "operator": "swap",
                "accepted": True,
                "score_base": 11.0,
                "score_new": 10.4,
                "health": {"score": 79.0, "sandbox_stability": 0.9},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    registry_payload = {
        "active": "life-a",
        "lives": {
            "life-a": LifeMetadata(
                name="Life A",
                slug="life-a",
                path=life_a,
                created_at="2026-05-11T08:00:00+00:00",
                status="active",
                parents=(),
                children=("life-b",),
                allies=("life-b",),
                rivals=(),
                proximity_score=0.8,
                lineage_depth=0,
            ),
            "life-b": LifeMetadata(
                name="Life B",
                slug="life-b",
                path=life_b,
                created_at="2026-05-11T08:10:00+00:00",
                status="active",
                parents=("life-a",),
                children=(),
                allies=("life-a",),
                rivals=(),
                proximity_score=0.5,
                lineage_depth=1,
            ),
        },
    }

    monkeypatch.setenv("SINGULAR_ROOT", str(root))
    monkeypatch.setenv("SINGULAR_HOME", str(life_a))
    monkeypatch.setattr("singular.dashboard.load_registry", lambda: registry_payload)

    app = create_app(psyche_file=life_a / "mem" / "psyche.json")
    return TestClient(app), {
        "active_run": active_run,
        "life_a": life_a,
        "life_b": life_b,
    }


def test_dashboard_index_exposes_interactive_contracts(tmp_path: Path) -> None:
    app = create_app(runs_dir=tmp_path / "runs", psyche_file=tmp_path / "psyche.json")
    response = TestClient(app).get("/")

    assert response.status_code == 200
    body = response.json()

    tab_contracts = {
        "tab-btn-decider": ("decider-maintenant", "tab-decider-maintenant"),
        "tab-btn-diagnostiquer": ("diagnostiquer", "tab-diagnostiquer"),
        "tab-btn-comparer": ("comparer-vies", "tab-comparer-vies"),
        "tab-btn-technique": ("technique", "tab-technique"),
    }
    assert "role='tablist'" in body
    for trigger_id, (tab_id, panel_id) in tab_contracts.items():
        assert f"id='{trigger_id}'" in body
        assert "class='tab-trigger'" in body
        assert f"data-tab='{tab_id}'" in body
        assert f"aria-controls='{panel_id}'" in body
        assert f"id='{panel_id}'" in body
        assert "role='tabpanel'" in body
        assert f"aria-labelledby='{trigger_id}'" in body

    for toggle_id in ("toggle-essential", "toggle-technical-details"):
        assert f"id='{toggle_id}'" in body
        assert "class='nav-mode-toggle'" in body
        assert "aria-pressed='false'" in body

    critical_actions = {
        "critical-birth": "birth",
        "critical-archive": "archive",
        "critical-talk": "talk",
        "critical-emergency-stop": "emergency_stop",
    }
    for action_id, action_name in critical_actions.items():
        assert f"id='{action_id}'" in body
        assert f"data-dashboard-action='{action_name}'" in body
    assert "id='critical-action-result'" in body
    assert "data-confirm=" in body
    assert "data-confirm-again=" in body

    for target_id in ("cockpit-detail-json", "cockpit-context-more"):
        assert f"data-expand-target='{target_id}'" in body
        assert f"id='{target_id}' class='panel-hidden'" in body
    assert "toggle-more-btn" in body
    assert "aria-expanded='false'" in body


def test_active_tmp_run_feeds_dashboard_endpoints(
    active_run_dashboard: tuple[TestClient, dict[str, Path]],
) -> None:
    client, paths = active_run_dashboard
    assert paths["active_run"].name.endswith(".jsonl.tmp")

    cockpit_response = client.get("/api/cockpit")
    assert cockpit_response.status_code == 200
    cockpit = cockpit_response.json()
    assert cockpit["run"] == "active-smoke"
    assert cockpit["health_score"] == 84.0
    assert cockpit["accepted_mutation_rate"] == 1.0
    assert cockpit["next_action"]
    assert cockpit["memory_metrics"]["has_memory_signal"] is True
    assert cockpit["performance_metrics"]["avg_latency_ms"] == 100.0
    assert cockpit["social_relations"]["alliance_edges"] >= 1
    assert cockpit["social_relations"]["resource_exchange_events"] == 1
    assert any(
        item["event"] == "orchestrator.decision" for item in cockpit["major_decisions"]
    )
    assert cockpit["vital_metrics"]["energy_resources"]["total_energy"] > 0
    assert cockpit["life_metrics_contract"]["counts"]["total_lives"] >= 2
    assert cockpit["life_status"] in {
        "running",
        "budget_exhausted",
        "degraded",
        "mutation_paused",
        "terminal",
        "dead",
    }
    assert isinstance(cockpit["life_status_score"], float)
    assert isinstance(cockpit["life_status_explanation"], str)

    context_response = client.get("/dashboard/context")
    assert context_response.status_code == 200
    context = context_response.json()
    assert context["registry_lives_count"] == 2
    assert context["registry_lives"]
    assert context["registry_state"]["active"] == "life-a"
    assert context["registry_state"]["active_valid"] is True

    ecosystem_response = client.get("/ecosystem")
    assert ecosystem_response.status_code == 200
    ecosystem = ecosystem_response.json()
    assert ecosystem["organisms"]["org-active"]["energy"] == 8
    assert ecosystem["summary"]["total_energy"] == 8.0
    assert ecosystem["life_metrics_contract"]["counts"]["alive_lives"] >= 1

    comparison_response = client.get("/lives/comparison")
    assert comparison_response.status_code == 200
    comparison = comparison_response.json()
    assert comparison["table"]
    assert {row["life"] for row in comparison["table"]} >= {"life-a", "life-b"}
    assert comparison["lives"]["life-a"]["current_health_score"] == 84.0
    assert comparison["life_metrics_contract"]["counts"]["total_lives"] >= 2
