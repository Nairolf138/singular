import json
import pytest

from graine.runs import capture_run, replay


def test_replay_is_deterministic(tmp_path):
    name = "demo"
    path = capture_run(seed=123, name=name, steps=3)

    snap_data = json.loads(path.read_text(encoding="utf-8"))
    reproduced = replay(path)
    assert reproduced == snap_data

    # Tamper with the stored seed to ensure mismatch is detected
    seeds_file = path.parent / "seeds.json"
    seeds_file.write_text(json.dumps({"seed": 321}), encoding="utf-8")
    with pytest.raises(RuntimeError):
        replay(path)
