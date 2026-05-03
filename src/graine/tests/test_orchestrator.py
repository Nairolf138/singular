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
    mutation_log = Path("life/meta_mutation_log")
    if mutation_log.exists():
        mutation_log.unlink()
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



def test_run_creates_meta_mutation_log(tmp_path: Path) -> None:
    spec = build_spec()
    snapshot_dir = tmp_path / "snaps"
    log_path = tmp_path / "run.log"
    mutation_log = Path("life/meta_mutation_log")
    if mutation_log.exists():
        mutation_log.unlink()
    final_spec = run(
        generations=2,
        meta=spec,
        adopt_every=1,
        snapshot_dir=snapshot_dir,
        log_path=log_path,
        rng=random.Random(1),
    )
    assert final_spec.validate()
    assert mutation_log.exists()
    entries = [json.loads(line) for line in mutation_log.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert entries
    last = entries[-1]
    assert "hypothesis" in last
    assert "mutable_surfaces" in last
    assert "patch" in last and "before" in last["patch"] and "after" in last["patch"]
    assert last["result"] in {"promoted", "rejected"}
