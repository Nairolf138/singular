from __future__ import annotations

import json
from pathlib import Path

import pytest

from singular.lives import (
    LifeMetadata,
    ally_lives,
    bootstrap_life,
    clone_life,
    get_registry_root,
    list_relations,
    load_registry,
    reconcile_lives,
    resolve_life,
    rival_lives,
    set_proximity,
    set_life_status,
)
from singular.organisms.birth import birth


def test_birth_uses_isolated_homes(tmp_path: Path) -> None:
    home1 = tmp_path / "vie1"
    home2 = tmp_path / "vie2"

    birth(home=home1)
    birth(home=home2)

    assert not (tmp_path / "id.json").exists()
    assert not (tmp_path / "mem").exists()
    assert not (tmp_path / "skills").exists()

    for home in (home1, home2):
        assert (home / "id.json").exists()
        assert (home / "mem" / "psyche.json").exists()
        assert (home / "skills").is_dir()


def test_registry_tracks_multiple_lives(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SINGULAR_ROOT", str(tmp_path))

    life1 = bootstrap_life("Vie 1", seed=1)
    life2 = bootstrap_life("Vie 2", seed=2)

    registry = load_registry()
    lives = registry["lives"]
    assert set(lives) == {life1.slug, life2.slug}
    assert registry["active"] == life2.slug
    assert lives[life1.slug].status == "active"
    assert lives[life2.slug].status == "active"

    assert resolve_life(None) == life2.path
    assert resolve_life(life1.name) == life1.path

    registry = load_registry()
    assert registry["active"] == life1.slug
    assert resolve_life(life2.slug) == life2.path

    registry = load_registry()
    assert registry["active"] == life2.slug

    registry_path = tmp_path / "lives" / "registry.json"
    assert registry_path.exists()
    assert registry_path.read_text(encoding="utf-8")


def test_registry_root_defaults_to_home_without_explicit_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SINGULAR_ROOT", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "mem").mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(workspace)

    assert get_registry_root() == tmp_path / "home" / ".singular"


def test_registry_root_uses_cwd_with_valid_registry_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SINGULAR_ROOT", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    workspace = tmp_path / "workspace"
    (workspace / "lives").mkdir(parents=True, exist_ok=True)
    (workspace / "lives" / "registry.json").write_text(
        '{"active": null, "lives": {}}',
        encoding="utf-8",
    )
    monkeypatch.chdir(workspace)

    assert get_registry_root() == workspace


def test_set_life_status_updates_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SINGULAR_ROOT", str(tmp_path))
    life = bootstrap_life("Vie test", seed=3)
    set_life_status(life.slug, "extinct")

    registry = load_registry()
    assert registry["lives"][life.slug].status == "extinct"


def test_load_registry_returns_default_for_empty_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("SINGULAR_ROOT", str(tmp_path))
    registry_path = tmp_path / "lives" / "registry.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text("", encoding="utf-8")

    registry = load_registry()

    assert registry == {"active": None, "lives": {}}
    assert "Failed to load life registry" in caplog.text


def test_load_registry_returns_default_for_invalid_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("SINGULAR_ROOT", str(tmp_path))
    registry_path = tmp_path / "lives" / "registry.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text("{invalid", encoding="utf-8")

    registry = load_registry()

    assert registry == {"active": None, "lives": {}}
    assert "Failed to load life registry" in caplog.text


def test_load_registry_handles_partial_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SINGULAR_ROOT", str(tmp_path))
    registry_path = tmp_path / "lives" / "registry.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text('{"active": "missing-slug"}', encoding="utf-8")

    registry = load_registry()

    assert registry == {"active": None, "lives": {}}


def test_life_metadata_from_payload_raises_for_missing_required_fields() -> None:
    with pytest.raises(ValueError, match="missing required field"):
        LifeMetadata.from_payload(
            {
                "slug": "alpha",
                "path": "/tmp/life-alpha",
                "created_at": "2026-01-01T00:00:00+00:00",
            }
        )


def test_life_metadata_from_payload_raises_for_bad_required_types() -> None:
    with pytest.raises(ValueError, match="non-empty strings"):
        LifeMetadata.from_payload(
            {
                "name": "Alpha",
                "slug": "alpha",
                "path": 123,
                "created_at": "2026-01-01T00:00:00+00:00",
            }
        )


def test_load_registry_skips_invalid_entries_with_logging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("SINGULAR_ROOT", str(tmp_path))
    registry_path = tmp_path / "lives" / "registry.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(
        json.dumps(
            {
                "active": "alpha",
                "lives": {
                    "alpha": {
                        "name": "Alpha",
                        "slug": "alpha",
                        "path": str(tmp_path / "lives" / "alpha"),
                        "created_at": "2026-01-01T00:00:00+00:00",
                    },
                    "broken": {
                        "name": "Broken",
                        "slug": "broken",
                        "created_at": "2026-01-01T00:00:00+00:00",
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    registry = load_registry()

    assert set(registry["lives"]) == {"alpha"}
    assert registry["active"] == "alpha"
    assert "Skipping invalid life entry 'broken'" in caplog.text


def test_relations_support_allies_rivals_children_and_proximity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SINGULAR_ROOT", str(tmp_path))
    alpha = bootstrap_life("Alpha")
    beta = bootstrap_life("Beta")
    gamma = bootstrap_life("Gamma")

    ally_lives(alpha.slug, beta.slug)
    rival_lives(alpha.slug, gamma.slug)
    set_proximity(alpha.slug, 0.83)
    reconcile_lives(alpha.slug, gamma.slug)

    payload = list_relations(alpha.slug)
    assert payload["focus"]["allies"] == [beta.slug]
    assert payload["focus"]["rivals"] == []
    assert payload["focus"]["proximity_score"] == 0.83
    assert any(node["slug"] == alpha.slug for node in payload["social"]["nodes"])


def test_clone_life_applies_inheritance_policy_and_logs_transfers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SINGULAR_ROOT", str(tmp_path))
    source = bootstrap_life("Source", seed=5)
    source_mem = source.path / "mem"
    source_skills = source.path / "skills"
    source_skills.mkdir(parents=True, exist_ok=True)
    (source_skills / "kept.py").write_text("def run(context=None):\n    return {'ok': True}\n", encoding="utf-8")
    (source_skills / "dropped.py").write_text("def run(context=None):\n    return {'ok': True}\n", encoding="utf-8")

    (source_mem / "skills.json").write_text(
        json.dumps(
            {
                "kept": {"score": 0.9, "inheritable": True},
                "dropped": {"score": 0.2, "inheritable": False},
            }
        ),
        encoding="utf-8",
    )
    (source_mem / "episodic.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"event": "quest", "status": "success", "mood": "joy"}),
                json.dumps({"event": "repair", "status": "failure", "token": "secret"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    clone = clone_life(source.slug, new_name="Source clone")
    clone_mem = clone.path / "mem"
    clone_skills = clone.path / "skills"

    inherited_skills = json.loads((clone_mem / "skills.json").read_text(encoding="utf-8"))
    assert list(inherited_skills) == ["kept"]
    assert (clone_skills / "kept.py").exists()
    assert not (clone_skills / "dropped.py").exists()

    memory_summary = json.loads((clone_mem / "legacy_memory_summary.json").read_text(encoding="utf-8"))
    assert len(memory_summary) == 1
    assert memory_summary[0]["event"] == "quest"

    lessons = json.loads((clone_mem / "legacy_lessons.json").read_text(encoding="utf-8"))
    assert lessons["success_count"] == 1
    assert lessons["failure_count"] == 0

    inheritance = json.loads((clone_mem / "inheritance_policy.json").read_text(encoding="utf-8"))
    assert "inheritance_policy" in inheritance
    assert inheritance["inherited_from"] == source.slug

    journal_path = tmp_path / "mem" / "legacy_transfers.jsonl"
    assert journal_path.exists()
    journal_lines = [json.loads(line) for line in journal_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(journal_lines) == 3
    assert all(item["source"] == source.slug for item in journal_lines)
    assert all(item["target"] == clone.slug for item in journal_lines)
    assert {item["reason"] for item in journal_lines} == {
        "non_sensitive_memory_summary",
        "inheritable_skills_only",
        "aggregated_success_failure_lessons",
    }
