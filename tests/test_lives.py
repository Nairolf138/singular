from __future__ import annotations

from pathlib import Path

import pytest

from singular.lives import bootstrap_life, load_registry, resolve_life
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
