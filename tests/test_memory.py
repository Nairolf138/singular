from pathlib import Path
import json
import multiprocessing as mp
from concurrent.futures import ThreadPoolExecutor

import pytest
from typing import Any

from singular.memory import (
    add_episode,
    apply_skill_maintenance,
    controlled_delete_skill,
    restore_skill,
    temporarily_disable_skill,
    update_note,
    update_score,
    update_trait,
    record_skill_metric,
)
import singular.memory as memory
from singular.organisms.birth import birth


def _append_episode_worker(path: str, start: int, count: int) -> None:
    for idx in range(start, start + count):
        add_episode({"event": "mp", "id": idx}, path=Path(path))


def test_birth_creates_memory_files(tmp_path: Path) -> None:
    birth(home=tmp_path)
    mem = tmp_path / "mem"
    assert mem.is_dir()
    for name in ["profile.json", "values.yaml", "episodic.jsonl", "skills.json", "skill_catalog.json"]:
        assert (mem / name).exists()


def test_birth_initializes_identity_profile_and_psyche(tmp_path: Path) -> None:
    birth(seed=123, home=tmp_path)

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
        "optimism": 0.5,
        "resilience": 0.5,
        "energy": 100.0,
        "last_mood": None,
    }


def test_add_episode(tmp_path: Path) -> None:
    episode_path = tmp_path / "mem" / "episodic.jsonl"
    add_episode({"event": "test"}, path=episode_path)
    lines = episode_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0]) == {"event": "test"}


def test_add_episode_concurrent_threads(tmp_path: Path) -> None:
    episode_path = tmp_path / "mem" / "episodic.jsonl"
    total = 80
    with ThreadPoolExecutor(max_workers=8) as pool:
        for idx in range(total):
            pool.submit(add_episode, {"event": "thread", "id": idx}, episode_path)

    lines = episode_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == total
    ids = {json.loads(line)["id"] for line in lines}
    assert ids == set(range(total))


def test_add_episode_concurrent_processes(tmp_path: Path) -> None:
    episode_path = tmp_path / "mem" / "episodic.jsonl"
    proc_count = 4
    per_proc = 20
    processes = [
        mp.Process(
            target=_append_episode_worker,
            args=(str(episode_path), proc_idx * per_proc, per_proc),
        )
        for proc_idx in range(proc_count)
    ]

    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=10)
        assert process.exitcode == 0

    lines = episode_path.read_text(encoding="utf-8").splitlines()
    expected = proc_count * per_proc
    assert len(lines) == expected
    ids = {json.loads(line)["id"] for line in lines}
    assert ids == set(range(expected))


def test_update_trait_score_and_note(tmp_path: Path) -> None:
    profile_path = tmp_path / "mem" / "profile.json"
    skills_path = tmp_path / "mem" / "skills.json"

    update_trait("courage", "high", path=profile_path)
    assert json.loads(profile_path.read_text(encoding="utf-8")) == {"courage": "high"}

    update_score("archery", 10, path=skills_path)
    update_note("archery", "bullseye", path=skills_path)
    assert json.loads(skills_path.read_text(encoding="utf-8")) == {
        "archery": {"score": 10, "note": "bullseye"}
    }


def test_birth_initializes_default_skills(tmp_path: Path) -> None:
    birth(home=tmp_path)

    skills_dir = tmp_path / "skills"
    expected_skill_names = [
        "addition",
        "subtraction",
        "multiplication",
        "validation",
        "summary",
        "intent_classification",
        "entity_extraction",
        "planning",
        "metrics",
    ]
    for name in expected_skill_names:
        assert (skills_dir / f"{name}.py").exists()

    skills_data = json.loads(
        (tmp_path / "mem" / "skills.json").read_text(encoding="utf-8")
    )
    assert skills_data == {name: {"score": 0.0} for name in expected_skill_names}

    catalog = json.loads((tmp_path / "mem" / "skill_catalog.json").read_text(encoding="utf-8"))
    assert set(catalog) >= set(expected_skill_names)


def test_values_helpers_without_yaml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Simulate missing PyYAML and ensure graceful handling."""
    import builtins
    import sys

    # Ensure ``yaml`` cannot be imported
    monkeypatch.delitem(sys.modules, "yaml", raising=False)

    real_import = builtins.__import__

    def fake_import(name: str, *args: Any, **kwargs: Any):  # type: ignore[override]
        if name == "yaml":
            raise ImportError("No module named 'yaml'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    values_path = tmp_path / "values.yaml"
    values_path.write_text("a: 1\n", encoding="utf-8")

    # Reading values without PyYAML should return an empty dict
    assert memory.read_values(values_path) == {}

    # Writing values should raise an informative ImportError
    with pytest.raises(ImportError):
        memory.write_values({"a": 1}, values_path)


def test_record_skill_metric_persists_longitudinal_fields(tmp_path: Path) -> None:
    skills_path = tmp_path / "mem" / "skills.json"
    update_score("alpha", 1.5, path=skills_path)

    record_skill_metric("alpha", gain=0.4, cost=12.0, success=True, path=skills_path)
    record_skill_metric("alpha", gain=-0.1, cost=8.0, success=False, path=skills_path)

    payload = json.loads(skills_path.read_text(encoding="utf-8"))
    metrics = payload["alpha"]["metrics"]
    assert metrics["usage_count"] == 2
    assert metrics["failure_count"] == 1
    assert metrics["average_gain"] == pytest.approx(0.15)
    assert metrics["average_cost"] == pytest.approx(10.0)
    assert isinstance(metrics["last_used_at"], str)


def test_skill_maintenance_archive_and_restore_is_lossless(tmp_path: Path) -> None:
    skills_path = tmp_path / "mem" / "skills.json"
    update_score("beta", 2.0, path=skills_path)
    record_skill_metric("beta", gain=0.6, cost=4.0, success=True, path=skills_path)

    data = json.loads(skills_path.read_text(encoding="utf-8"))
    data["beta"]["metrics"]["last_used_at"] = "2020-01-01T00:00:00+00:00"
    skills_path.parent.mkdir(parents=True, exist_ok=True)
    skills_path.write_text(json.dumps(data), encoding="utf-8")

    apply_skill_maintenance(dormant_after_days=5, archive_after_days=30, path=skills_path)
    archived = json.loads(skills_path.read_text(encoding="utf-8"))
    assert archived["beta"]["lifecycle"]["state"] == "archived"
    assert archived["beta"]["metrics"]["usage_count"] == 1
    assert archived["beta"]["metrics"]["average_gain"] == pytest.approx(0.6)

    restore_skill("beta", path=skills_path)
    restored = json.loads(skills_path.read_text(encoding="utf-8"))
    assert restored["beta"]["lifecycle"]["state"] == "active"
    assert restored["beta"]["metrics"]["usage_count"] == 1
    assert restored["beta"]["metrics"]["average_gain"] == pytest.approx(0.6)


def test_skill_temporary_disable_and_controlled_delete(tmp_path: Path) -> None:
    skills_path = tmp_path / "mem" / "skills.json"
    update_score("gamma", 0.2, path=skills_path)

    temporarily_disable_skill("gamma", duration_hours=2, reason="cooldown", path=skills_path)
    disabled = json.loads(skills_path.read_text(encoding="utf-8"))
    assert disabled["gamma"]["lifecycle"]["state"] == "temporarily_disabled"
    assert disabled["gamma"]["lifecycle"]["disabled_until"] is not None

    controlled_delete_skill("gamma", reason="governance_cleanup", path=skills_path)
    deleted = json.loads(skills_path.read_text(encoding="utf-8"))
    assert deleted["gamma"]["lifecycle"]["state"] == "deleted"
    snapshot = deleted["gamma"]["lifecycle"]["snapshot_path"]
    assert isinstance(snapshot, str)
    assert Path(snapshot).exists()
