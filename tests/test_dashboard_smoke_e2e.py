from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastapi_stub import TestClient

from singular.dashboard import create_app
from singular.lives import LifeMetadata


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

    timeline_payload = app._routes["/api/runs/{run_id}/timeline"](run_id=run_id)
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
