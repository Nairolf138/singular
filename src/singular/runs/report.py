"""Utilities for summarizing run performance."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
import json
from typing import Any

from .logger import RUNS_DIR
from ..life.health import detect_health_state
from ..memory import read_skills, get_skills_file


def load_run_records(
    run_id: str, runs_dir: Path | str = RUNS_DIR
) -> list[dict[str, Any]]:
    """Load run records for ``run_id`` from JSONL log file."""
    runs_dir = Path(runs_dir)
    event_path = runs_dir / run_id / "events.jsonl"
    records: list[dict[str, Any]] = []
    if event_path.exists():
        with event_path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                event = json.loads(line)
                payload = event.get("payload", {})
                if isinstance(payload, dict):
                    records.append({**payload, "_event_type": event.get("event_type")})
        return records

    pattern = f"{run_id}-*.jsonl"
    files = sorted(runs_dir.glob(pattern))
    if not files:
        raise FileNotFoundError(f"No log file found for id {run_id}")
    path = files[-1]
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records


def report(
    run_id: str,
    *,
    runs_dir: Path | str = RUNS_DIR,
    skills_path: Path | str | None = None,
    output_format: str = "plain",
) -> None:
    """Summarize performance for a given run."""

    try:
        records = load_run_records(run_id, runs_dir)
    except FileNotFoundError:
        print(f"No run log found for id {run_id}")
        return

    if not records:
        print(f"No records for id {run_id}")
        return

    mutations = [
        r for r in records if r.get("_event_type") == "mutation" or "op" in r
    ]
    if not mutations:
        print(f"No mutation records for id {run_id}")
        return

    scores = [r.get("score_new", 0.0) for r in mutations]
    ops = [r.get("op", "?") for r in mutations]
    counter = Counter(ops)

    health_scores = [
        float(h["score"])
        for r in mutations
        for h in [r.get("health", {})]
        if isinstance(h, dict) and isinstance(h.get("score"), (int, float))
    ]
    payload: dict[str, Any] = {
        "run_id": run_id,
        "generations": len(scores),
        "final_score": scores[-1],
        "best_score": min(scores),  # Lower score is better.
        "health": None,
        "operator_histogram": dict(counter),
    }
    if health_scores:
        health_state = detect_health_state(health_scores, short_window=10, long_window=50)
        payload["health"] = {
            "score": round(health_scores[-1], 2),
            "trend": health_state,
            "window": "10/50",
        }

    if output_format == "json":
        if skills_path is None:
            skills_path = get_skills_file()
        payload["skills"] = read_skills(path=skills_path)
        print(json.dumps(payload, ensure_ascii=False))
        return

    print(f"Run {run_id}")
    print(f"Generations: {len(scores)}")
    print(f"Final score: {scores[-1]}")
    print(f"Best score: {min(scores)}")
    if payload["health"]:
        print(
            "Health: "
            f"{payload['health']['score']:.2f}/100 "
            f"({payload['health']['trend']}, comparaison fenêtres {payload['health']['window']})"
        )
    if output_format == "table":
        print("Operator histogram:")
        for op, count in sorted(counter.items()):
            print(f"{op:<24} {count:>4}")
    else:
        print("Operator histogram:")
        for op, count in counter.items():
            print(f"  {op}: {count}")

    _print_loop_modifications(mutations)

    if skills_path is None:
        skills_path = get_skills_file()
    skills = read_skills(path=skills_path)
    if skills:
        print("Skills:")
        for skill, data in skills.items():
            if isinstance(data, dict):
                score = data.get("score")
                note = data.get("note")
            else:
                score = data
                note = None
            line = f"  {skill}: {score}"
            if note:
                line += f" ({note})"
            print(line)
    else:
        print("No skills recorded.")


def _print_loop_modifications(mutations: list[dict[str, Any]]) -> None:
    """Print ranked mutation-impact metrics for the loop."""

    entries: list[dict[str, Any]] = []
    for idx, mutation in enumerate(mutations, start=1):
        metrics = mutation.get("loop_modifications")
        if not isinstance(metrics, dict) or not metrics:
            continue
        lines_added = int(metrics.get("lines_added", 0))
        lines_removed = int(metrics.get("lines_removed", 0))
        functions_modified = int(metrics.get("functions_modified", 0))
        ast_before = int(metrics.get("ast_nodes_before", 0))
        ast_after = int(metrics.get("ast_nodes_after", 0))
        entries.append(
            {
                "index": idx,
                "op": mutation.get("op", "?"),
                "lines_added": lines_added,
                "lines_removed": lines_removed,
                "functions_modified": functions_modified,
                "ast_before": ast_before,
                "ast_after": ast_after,
                "line_change": lines_added + lines_removed,
                "ast_delta": abs(ast_after - ast_before),
                "profit": float(mutation.get("score_base", 0.0))
                - float(mutation.get("score_new", 0.0)),
            }
        )

    if not entries:
        return

    print("Modifications de boucle:")

    biggest = sorted(
        entries,
        key=lambda e: (e["line_change"], e["ast_delta"], e["functions_modified"]),
        reverse=True,
    )
    print("  Plus gros changement:")
    for entry in biggest[:3]:
        print(
            f"    #{entry['index']} {entry['op']} "
            f"(lignes +{entry['lines_added']}/-{entry['lines_removed']}, "
            f"fonctions={entry['functions_modified']}, "
            f"AST {entry['ast_before']}→{entry['ast_after']})"
        )

    frequency = Counter(entry["op"] for entry in entries)
    print("  Plus fréquent:")
    for op, count in sorted(frequency.items(), key=lambda item: (-item[1], item[0]))[:3]:
        print(f"    {op}: {count}")

    profitable = sorted(entries, key=lambda e: e["profit"], reverse=True)
    print("  Plus rentable:")
    for entry in profitable[:3]:
        print(
            f"    #{entry['index']} {entry['op']} "
            f"(gain={entry['profit']:.4f}, "
            f"lignes={entry['line_change']}, ASTΔ={entry['ast_delta']})"
        )
