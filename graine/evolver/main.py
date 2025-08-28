"""Orchestrator for evolutionary runs.

This module coordinates patch generation, selection and meta-rule evolution.
Each generation is logged using a hash chained JSONL logger and a snapshot is
written to disk capturing the current meta rules and history. Meta rules are
mutated and conditionally adopted every ``K`` generations.
"""

from __future__ import annotations

import json
import random
from dataclasses import asdict
from pathlib import Path
from typing import List

from .generate import propose_mutations
from .select import Candidate, select
from .dsl import Patch
from ..kernel.logger import JsonlLogger
from ..meta.dsl import MetaSpec
from ..meta.evolve import propose_mutation as mutate_meta


def _patch_label(index: int, patch: Patch) -> str:
    """Return a stable label for ``patch``."""

    target = patch.target
    file = target.get("file", "")
    func = target.get("function", "")
    return f"{index}:{file}:{func}" if file or func else f"{index}"


def run(
    generations: int,
    meta: MetaSpec,
    adopt_every: int,
    snapshot_dir: Path,
    log_path: Path,
    rng: random.Random | None = None,
) -> MetaSpec:
    """Execute an evolutionary run.

    Parameters
    ----------
    generations:
        Number of generations to execute.
    meta:
        Initial meta specification controlling operator mix and weights.
    adopt_every:
        Interval at which mutated meta rules are proposed for adoption.
    snapshot_dir:
        Directory where per-generation snapshots are written.
    log_path:
        Location of the JSONL log file.
    rng:
        Optional random number generator for deterministic behaviour.

    Returns
    -------
    MetaSpec
        The final (possibly mutated) meta specification.
    """

    rng = rng or random.Random()
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = JsonlLogger(log_path)

    best: Candidate | None = None
    history: List[dict] = []

    for gen in range(1, generations + 1):
        patches = propose_mutations()
        candidates: List[Candidate] = []
        for i, patch in enumerate(patches):
            try:
                patch.validate()
            except Exception:
                continue
            objectives = {"err": rng.random(), "cost": rng.random()}
            cand = Candidate(
                patch,
                objectives,
                thresholds={"tests": True},
                name=_patch_label(i, patch),
            )
            candidates.append(cand)

        best = select(candidates, best)
        record = {
            "generation": gen,
            "chosen": str(best) if best else None,
            "objectives": best.objectives if best else {},
            "patch": {
                "target": best.patch.target if best else {},
                "ops": [op.name for op in best.patch.ops] if best else [],
            },
        }
        history.append(record)
        logger.log({"event": "generation", **record})

        snapshot_path = snapshot_dir / f"gen_{gen:04}.json"
        snapshot = {
            "meta": asdict(meta),
            "history": history,
        }
        snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")

        if gen % adopt_every == 0:
            proposed = mutate_meta(meta, rng=rng)
            if proposed.population_cap >= meta.population_cap:
                meta = proposed
                logger.log({"event": "meta_adopted", "generation": gen})
            else:
                logger.log({"event": "meta_rejected", "generation": gen})

    return meta


def main() -> None:  # pragma: no cover - convenience entry point
    """Run a small demonstration evolution."""

    spec = MetaSpec.from_dict(
        {
            "weights": {"perf": 0.5, "robust": 0.5},
            "operator_mix": {"CONST_TUNE": 0.5, "EQ_REWRITE": 0.5},
            "population_cap": 10,
            "selection_strategy": "elitism",
        }
    )
    spec.validate()

    from ..runs.replay import SNAPSHOT_DIR, LOG_DIR

    run(
        generations=5,
        meta=spec,
        adopt_every=2,
        snapshot_dir=SNAPSHOT_DIR,
        log_path=LOG_DIR / "evolver.log",
    )


if __name__ == "__main__":  # pragma: no cover - module executable
    main()
