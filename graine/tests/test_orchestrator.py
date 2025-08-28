import json
import random
from pathlib import Path

from graine.evolver.main import run
from graine.meta.dsl import MetaSpec


def build_spec() -> MetaSpec:
    data = {
        "weights": {"perf": 0.5, "robust": 0.5},
        "operator_mix": {"CONST_TUNE": 0.5, "EQ_REWRITE": 0.5},
        "population_cap": 10,
        "selection_strategy": "elitism",
    }
    spec = MetaSpec.from_dict(data)
    spec.validate()
    return spec


def test_run_logs_and_snapshots(tmp_path: Path) -> None:
    spec = build_spec()
    snapshot_dir = tmp_path / "snaps"
    log_path = tmp_path / "run.log"
    rng = random.Random(0)
    final_spec = run(
        generations=2,
        meta=spec,
        adopt_every=1,
        snapshot_dir=snapshot_dir,
        log_path=log_path,
        rng=rng,
    )
    assert final_spec.validate()

    snap1 = snapshot_dir / "gen_0001.json"
    snap2 = snapshot_dir / "gen_0002.json"
    assert snap1.exists()
    assert snap2.exists()
    data = json.loads(snap1.read_text(encoding="utf-8"))
    assert "meta" in data and "history" in data
    assert log_path.exists()
    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert any('"event": "generation"' in line for line in lines)
