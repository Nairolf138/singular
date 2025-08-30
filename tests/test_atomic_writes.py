import json
import os
from pathlib import Path

import pytest

from singular import memory
from singular.resource_manager import ResourceManager


def failing_replace(src, dst):
    raise RuntimeError("boom")


def test_write_profile_atomic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    profile_path = tmp_path / "mem" / "profile.json"
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(json.dumps({"old": 1}), encoding="utf-8")

    monkeypatch.setattr(memory.os, "replace", failing_replace)

    with pytest.raises(RuntimeError):
        memory.write_profile({"new": 2}, path=profile_path)

    assert json.loads(profile_path.read_text(encoding="utf-8")) == {"old": 1}


def test_add_episode_atomic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    episode_path = tmp_path / "mem" / "episodic.jsonl"
    episode_path.parent.mkdir(parents=True, exist_ok=True)
    episode_path.write_text(json.dumps({"event": "old"}) + "\n", encoding="utf-8")

    monkeypatch.setattr(memory.os, "replace", failing_replace)

    with pytest.raises(RuntimeError):
        memory.add_episode({"event": "new"}, path=episode_path)

    lines = episode_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0]) == {"event": "old"}


def test_resource_manager_save_atomic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "resources.json"
    path.write_text(
        json.dumps({"energy": 1, "food": 2, "warmth": 3}), encoding="utf-8"
    )
    rm = ResourceManager(path=path)

    monkeypatch.setattr(memory.os, "replace", failing_replace)

    rm.energy = 10
    with pytest.raises(RuntimeError):
        rm._save()

    assert json.loads(path.read_text(encoding="utf-8")) == {
        "energy": 1,
        "food": 2,
        "warmth": 3,
    }
