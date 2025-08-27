import json
import pytest

from graine.runs import capture_run, replay


def test_replay_is_deterministic():
    name = "demo"
    path = capture_run(seed=123, name=name, steps=3)
    snap_data = json.loads(path.read_text(encoding="utf-8"))
    reproduced = replay(path, seed=123)
    assert reproduced == snap_data

    with pytest.raises(RuntimeError):
        replay(path, seed=321)
