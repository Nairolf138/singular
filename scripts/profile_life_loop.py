#!/usr/bin/env python3
"""Profile the Singular life loop on a temporary life for a fixed tick count."""

from __future__ import annotations

import argparse
import json
import os
import random
import tempfile
from pathlib import Path


def _write_temporary_life(root: Path) -> tuple[Path, Path]:
    skills_dir = root / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)
    (skills_dir / "toy_skill.py").write_text(
        "def toy_skill(x=1):\n    return x + 1\n",
        encoding="utf-8",
    )
    checkpoint = root / "life_checkpoint.json"
    return skills_dir, checkpoint


def _phase_records(runs_dir: Path, run_id: str) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for path in sorted(runs_dir.glob(f"{run_id}-*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict) and payload.get("event") == "life_loop_phase_metrics":
                records.append(payload)
    return records


def _aggregate(records: list[dict[str, object]]) -> dict[str, object]:
    phase_totals: dict[str, float] = {}
    phase_calls: dict[str, int] = {}
    cache_hits: dict[str, int] = {}
    cache_misses: dict[str, int] = {}
    candidates: list[dict[str, object]] = []
    async_note = None
    for record in records:
        metrics = record.get("phase_metrics")
        if not isinstance(metrics, dict):
            continue
        async_note = metrics.get("async_distribution_note") or async_note
        if isinstance(metrics.get("cache_candidates"), list):
            candidates = metrics["cache_candidates"]
        phases = metrics.get("phases")
        if not isinstance(phases, dict):
            continue
        for name, raw in phases.items():
            if not isinstance(raw, dict):
                continue
            phase = str(name)
            phase_totals[phase] = phase_totals.get(phase, 0.0) + float(raw.get("total_ms", 0.0) or 0.0)
            phase_calls[phase] = phase_calls.get(phase, 0) + int(raw.get("calls", 0) or 0)
            cache_hits[phase] = cache_hits.get(phase, 0) + int(raw.get("cache_hits", 0) or 0)
            cache_misses[phase] = cache_misses.get(phase, 0) + int(raw.get("cache_misses", 0) or 0)
    phases = {
        phase: {
            "total_ms": round(total, 3),
            "calls": phase_calls.get(phase, 0),
            "avg_ms": round(total / phase_calls[phase], 3) if phase_calls.get(phase) else 0.0,
            "cache_hits": cache_hits.get(phase, 0),
            "cache_misses": cache_misses.get(phase, 0),
        }
        for phase, total in sorted(phase_totals.items(), key=lambda item: item[1], reverse=True)
    }
    return {
        "ticks_profiled": len(records),
        "slowest_phase": next(iter(phases), None),
        "phases": phases,
        "cache_candidates": candidates,
        "async_distribution_note": async_note
        or "Étudier async/distribué uniquement après métriques fiables.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Profile life loop phases on a temporary life")
    parser.add_argument("--ticks", type=int, default=5, help="fixed number of life-loop ticks")
    parser.add_argument("--run-id", default="profile-life-loop", help="run id used for JSONL logs")
    parser.add_argument("--seed", type=int, default=7, help="deterministic random seed")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="singular-life-profile-") as tmp:
        root = Path(tmp)
        skills_dir, checkpoint = _write_temporary_life(root)
        previous_home = os.environ.get("SINGULAR_HOME")
        previous_cwd = Path.cwd()
        os.environ["SINGULAR_HOME"] = str(root)
        os.chdir(root)
        try:
            from singular.life.loop import run

            run(
                skills_dirs=skills_dir,
                checkpoint_path=checkpoint,
                budget_seconds=max(1.0, args.ticks * 0.5),
                rng=random.Random(args.seed),
                run_id=args.run_id,
                max_iterations=max(1, args.ticks),
            )
            records = _phase_records(root / "runs", args.run_id)
            print(json.dumps(_aggregate(records), ensure_ascii=False, indent=2))
        finally:
            os.chdir(previous_cwd)
            if previous_home is None:
                os.environ.pop("SINGULAR_HOME", None)
            else:
                os.environ["SINGULAR_HOME"] = previous_home


if __name__ == "__main__":
    main()
