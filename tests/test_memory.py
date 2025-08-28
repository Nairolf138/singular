from pathlib import Path
import json

import pytest

from singular.memory import add_episode, update_trait, update_score
from singular.organisms.birth import birth


def test_birth_creates_memory_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    birth()
    mem = tmp_path / "mem"
    assert mem.is_dir()
    for name in ["profile.json", "values.yaml", "episodic.jsonl", "skills.json"]:
        assert (mem / name).exists()


def test_birth_initializes_identity_profile_and_psyche(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    birth(seed=123)

    identity_data = json.loads((tmp_path / "id.json").read_text(encoding="utf-8"))
    profile_data = json.loads(
        (tmp_path / "mem" / "profile.json").read_text(encoding="utf-8")
    )
    assert profile_data["id"] == identity_data["id"]

    psyche_data = json.loads(
        (tmp_path / "mem" / "psyche.json").read_text(encoding="utf-8")
    )
    assert psyche_data == {
        "curiosity": 0.5,
        "patience": 0.5,
        "playfulness": 0.5,
        "last_mood": None,
    }


def test_add_episode(tmp_path: Path) -> None:
    episode_path = tmp_path / "mem" / "episodic.jsonl"
    add_episode({"event": "test"}, path=episode_path)
    lines = episode_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0]) == {"event": "test"}


def test_update_trait_and_score(tmp_path: Path) -> None:
    profile_path = tmp_path / "mem" / "profile.json"
    skills_path = tmp_path / "mem" / "skills.json"

    update_trait("courage", "high", path=profile_path)
    assert json.loads(profile_path.read_text(encoding="utf-8")) == {"courage": "high"}

    update_score("archery", 10, path=skills_path)
    assert json.loads(skills_path.read_text(encoding="utf-8")) == {"archery": 10}


def test_birth_initializes_default_skills(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    birth()

    skills_dir = tmp_path / "skills"
    assert (skills_dir / "addition.py").exists()
    assert (skills_dir / "subtraction.py").exists()
    assert (skills_dir / "multiplication.py").exists()

    skills_data = json.loads(
        (tmp_path / "mem" / "skills.json").read_text(encoding="utf-8")
    )
    assert skills_data == {
        "addition": 0.0,
        "subtraction": 0.0,
        "multiplication": 0.0,
    }
