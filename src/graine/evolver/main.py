"""Orchestrator for evolutionary runs."""

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
from ..meta.dsl import MetaSpec, ALLOWED_MUTABLE_SURFACES
from ..meta.evolve import propose_mutation as mutate_meta
from ..meta.phantom import replay_snapshots


META_MUTATION_LOG = Path("life/meta_mutation_log")


def _patch_label(index: int, patch: Patch) -> str:
    target = patch.target
    file = target.get("file", "")
    func = target.get("function", "")
    return f"{index}:{file}:{func}" if file or func else f"{index}"


def _validate_meta_invariants(candidate: MetaSpec, baseline: MetaSpec) -> bool:
    candidate.validate()
    if candidate.diff_max != baseline.diff_max:
        raise ValueError("Constitutional invariant diff_max changed")
    if set(candidate.forbidden) != set(baseline.forbidden):
        raise ValueError("Constitutional forbidden list changed")
    return True


def _append_meta_mutation(entry: dict) -> None:
    META_MUTATION_LOG.parent.mkdir(parents=True, exist_ok=True)
    with META_MUTATION_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def run(
    generations: int,
    meta: MetaSpec,
    adopt_every: int,
    snapshot_dir: Path,
    log_path: Path,
    rng: random.Random | None = None,
) -> MetaSpec:
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
        snapshot = {"meta": asdict(meta), "history": history}
        snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")

        if gen % adopt_every == 0:
            baseline = meta
            proposed = mutate_meta(meta, rng=rng)
            hypothesis = "Allowed architectural patch can improve search without safety regression"
            result = "rejected"
            impact = "none"
            try:
                # 1) sandbox simulation
                sandbox_metrics = replay_snapshots(3, directory=snapshot_dir)
                # 2) invariant validation
                _validate_meta_invariants(proposed, baseline)
                # 3) rollback automatic via baseline retained unless promoted
                # 4) conditional promotion
                if proposed.population_cap >= baseline.population_cap and sandbox_metrics["safety"] >= 0:
                    meta = proposed
                    result = "promoted"
                    impact = "potential long-term exploration gain"
                    logger.log({"event": "meta_adopted", "generation": gen})
                else:
                    logger.log({"event": "meta_rejected", "generation": gen})
            except Exception as exc:
                logger.log({"event": "meta_rollback", "generation": gen, "error": str(exc)})
            _append_meta_mutation(
                {
                    "generation": gen,
                    "hypothesis": hypothesis,
                    "mutable_surfaces": sorted(ALLOWED_MUTABLE_SURFACES),
                    "patch": {"before": asdict(baseline), "after": asdict(proposed)},
                    "result": result,
                    "long_term_impact": impact,
                }
            )

    return meta
