import json
from contextlib import contextmanager
from pathlib import Path

import pytest

from singular import memory
from singular import io_utils
from singular.resource_manager import ResourceManager


def failing_replace(src, dst):
    raise RuntimeError("boom")


def test_write_profile_atomic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    profile_path = tmp_path / "mem" / "profile.json"
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(json.dumps({"old": 1}), encoding="utf-8")

    monkeypatch.setattr(io_utils.os, "replace", failing_replace)

    with pytest.raises(RuntimeError):
        memory.write_profile({"new": 2}, path=profile_path)

    assert json.loads(profile_path.read_text(encoding="utf-8")) == {"old": 1}


def test_add_episode_uses_append_path_not_snapshot_replace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    episode_path = tmp_path / "mem" / "episodic.jsonl"
    episode_path.parent.mkdir(parents=True, exist_ok=True)
    episode_path.write_text(json.dumps({"event": "old"}) + "\n", encoding="utf-8")

    monkeypatch.setattr(io_utils.os, "replace", failing_replace)

    memory.add_episode({"event": "new"}, path=episode_path)

    lines = episode_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0]) == {"event": "old"}
    assert json.loads(lines[1]) == {"event": "new"}


def test_resource_manager_save_atomic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "resources.json"
    path.write_text(json.dumps({"energy": 1, "food": 2, "warmth": 3}), encoding="utf-8")
    rm = ResourceManager(path=path)

    monkeypatch.setattr(io_utils.os, "replace", failing_replace)

    rm.energy = 10
    with pytest.raises(RuntimeError):
        rm._save()

    assert json.loads(path.read_text(encoding="utf-8")) == {
        "energy": 1,
        "food": 2,
        "warmth": 3,
    }


def test_atomic_write_text_retries_permission_error_on_windows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "state.json"
    destination.write_text('{"old": true}', encoding="utf-8")
    original_replace = io_utils.os.replace
    attempts = 0
    delays: list[float] = []

    def flaky_replace(src, dst):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise PermissionError("Access denied")
        return original_replace(src, dst)

    monkeypatch.setattr(io_utils, "_is_windows", lambda: True)
    monkeypatch.setattr(io_utils.os, "replace", flaky_replace)
    monkeypatch.setattr(io_utils.time, "sleep", delays.append)

    io_utils.atomic_write_text(destination, '{"new": true}')

    assert attempts == 3
    assert delays == [0.025, 0.05]
    assert json.loads(destination.read_text(encoding="utf-8")) == {"new": True}


def test_atomic_write_text_retries_winerror_5_oserror_on_windows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "state.json"
    destination.write_text('{"old": true}', encoding="utf-8")
    original_replace = io_utils.os.replace
    attempts = 0
    delays: list[float] = []

    def flaky_replace(src, dst):
        nonlocal attempts
        attempts += 1
        if attempts < 5:
            error = OSError("Access denied")
            error.winerror = 5
            raise error
        return original_replace(src, dst)

    monkeypatch.setattr(io_utils, "_is_windows", lambda: True)
    monkeypatch.setattr(io_utils.os, "replace", flaky_replace)
    monkeypatch.setattr(io_utils.time, "sleep", delays.append)

    io_utils.atomic_write_text(destination, '{"new": true}')

    assert attempts == 5
    assert delays == [0.025, 0.05, 0.1, 0.2]
    assert json.loads(destination.read_text(encoding="utf-8")) == {"new": True}


def test_atomic_write_text_windows_retry_raises_enriched_initial_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "state.json"
    destination.write_text('{"old": true}', encoding="utf-8")
    attempts = 0
    delays: list[float] = []

    def always_failing_replace(_src, _dst):
        nonlocal attempts
        attempts += 1
        raise PermissionError("Access denied")

    @contextmanager
    def fake_lock(_path: Path):
        yield

    monkeypatch.setattr(io_utils, "_is_windows", lambda: True)
    monkeypatch.setattr(io_utils, "_locked_file", fake_lock)
    monkeypatch.setattr(io_utils.os, "replace", always_failing_replace)
    monkeypatch.setattr(io_utils.time, "sleep", delays.append)

    with pytest.raises(PermissionError) as exc_info:
        io_utils.atomic_write_text(destination, '{"new": true}')

    assert attempts == 9
    assert delays == [0.025, 0.05, 0.1, 0.2, 0.4, 0.4, 0.4]
    notes = getattr(exc_info.value, "__notes__", [])
    assert any(
        "sidecar-lock fallback" in note
        and "attempts=8" in note
        and str(destination) in note
        and "delays=" in note
        for note in notes
    )
    assert json.loads(destination.read_text(encoding="utf-8")) == {"old": True}


def test_atomic_write_text_non_windows_permission_error_not_retried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "state.json"
    destination.write_text('{"old": true}', encoding="utf-8")
    attempts = 0
    delays: list[float] = []

    def failing_replace(_src, _dst):
        nonlocal attempts
        attempts += 1
        raise PermissionError("denied")

    monkeypatch.setattr(io_utils, "_is_windows", lambda: False)
    monkeypatch.setattr(io_utils.os, "replace", failing_replace)
    monkeypatch.setattr(io_utils.time, "sleep", delays.append)

    with pytest.raises(PermissionError):
        io_utils.atomic_write_text(destination, '{"new": true}')

    assert attempts == 1
    assert delays == []
    assert json.loads(destination.read_text(encoding="utf-8")) == {"old": True}
