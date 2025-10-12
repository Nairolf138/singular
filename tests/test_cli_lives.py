from pathlib import Path

import pytest

from singular.cli import main
from singular.lives import load_registry, resolve_life
from singular.memory import read_episodes


def test_lives_management(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = tmp_path / "universe"
    monkeypatch.delenv("SINGULAR_ROOT", raising=False)
    monkeypatch.delenv("SINGULAR_HOME", raising=False)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.setattr("singular.organisms.talk.load_llm_provider", lambda _name: None)

    main(["--root", str(root), "lives", "create", "--name", "Alpha"])
    registry = load_registry()
    alpha_slug = registry["active"]
    assert isinstance(alpha_slug, str)
    alpha_meta = registry["lives"][alpha_slug]
    alpha_path = Path(alpha_meta.path)

    main(["--root", str(root), "lives", "create", "--name", "Beta"])
    registry = load_registry()
    beta_slug = registry["active"]
    assert isinstance(beta_slug, str)
    beta_meta = registry["lives"][beta_slug]
    beta_path = Path(beta_meta.path)
    assert beta_slug != alpha_slug

    beta_before = list(read_episodes(beta_path / "mem" / "episodic.jsonl"))

    main(["--root", str(root), "lives", "use", alpha_meta.slug])
    registry = load_registry()
    assert registry["active"] == alpha_meta.slug

    main(["--root", str(root), "talk", "--prompt", "bonjour"])

    alpha_episodes = read_episodes(alpha_path / "mem" / "episodic.jsonl")
    assert any(
        episode.get("role") == "user" and episode.get("text") == "bonjour"
        for episode in alpha_episodes
    )
    beta_after = read_episodes(beta_path / "mem" / "episodic.jsonl")
    assert beta_before == beta_after

    main(["--root", str(root), "lives", "delete", beta_meta.slug])
    registry = load_registry()
    assert registry["active"] == alpha_meta.slug
    assert not beta_path.exists()
    assert resolve_life(None) == alpha_path
