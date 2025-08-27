from __future__ import annotations

"""Generate static HTML reports from run snapshots."""

import json
from pathlib import Path
from typing import Iterable, Dict, List

from .replay import SNAPSHOT_DIR, REPORT_DIR


def _pareto_front(points: List[Dict[str, float]]) -> List[Dict[str, float]]:
    front: List[Dict[str, float]] = []
    for p in points:
        if not any(
            (q["err"] <= p["err"] and q["cost"] <= p["cost"] and (q["err"] < p["err"] or q["cost"] < p["cost"]))
            for q in points
            if q is not p
        ):
            front.append(p)
    return front


def _delta_perf(history: List[Dict[str, float]]) -> List[float]:
    deltas: List[float] = []
    prev = history[0]["err"]
    for record in history[1:]:
        current = record["err"]
        deltas.append(current - prev)
        prev = current
    return deltas


def generate_report(snapshot_paths: Iterable[Path] | None = None, out_path: Path | None = None) -> Path:
    """Create a simple HTML report summarising Pareto fronts and Δperf curves."""

    if snapshot_paths is None:
        snapshot_paths = SNAPSHOT_DIR.glob("*/snapshot.json")

    paths = list(snapshot_paths)
    snaps = [(p, json.loads(p.read_text(encoding="utf-8"))) for p in paths]
    named_snaps = [(p.parent.name if p.name == "snapshot.json" else p.stem, s) for p, s in snaps]
    points = [
        {"name": name, "err": snap["history"][-1]["err"], "cost": snap["history"][-1]["cost"]}
        for name, snap in named_snaps
    ]
    front = _pareto_front(points)

    html: List[str] = ["<html><body>", "<h1>Run Report</h1>", "<h2>Pareto Front</h2>", "<ul>"]
    for p in front:
        html.append(f"<li>{p['name']}: err={p['err']:.4f}, cost={p['cost']:.4f}</li>")
    html.append("</ul><h2>Δperf curves</h2>")
    for name, snap in named_snaps:
        deltas = _delta_perf(snap["history"])
        html.append(f"<h3>{name}</h3><pre>{deltas}</pre>")
    html.append("</body></html>")

    if out_path is None:
        out_path = REPORT_DIR / "report.html"
    out_path.write_text("\n".join(html), encoding="utf-8")
    return out_path


__all__ = ["generate_report"]
