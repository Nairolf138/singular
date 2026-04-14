from __future__ import annotations

from pathlib import Path

import pytest

from singular.lives import (
    ally_lives,
    bootstrap_life,
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
