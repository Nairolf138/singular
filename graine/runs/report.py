"""Generate static reports and KPI exports from run snapshots."""

from __future__ import annotations

import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Dict, List, Any, Tuple

from .replay import SNAPSHOT_DIR, REPORT_DIR


def _pareto_front(points: List[Dict[str, float]]) -> List[Dict[str, float]]:
    front: List[Dict[str, float]] = []
    for p in points:
        if not any(
            (
                q["err"] <= p["err"]
                and q["cost"] <= p["cost"]
                and (q["err"] < p["err"] or q["cost"] < p["cost"])
            )
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


def _acceptance_rates(operations: Iterable[Dict[str, Any]] | None) -> Dict[str, float]:
    counts: Dict[str, Tuple[int, int]] = defaultdict(lambda: [0, 0])
    if operations is None:
        return {}
    for op in operations:
        name = op.get("operator")
        if name is None:
            continue
        acc, tot = counts[name]
        counts[name] = (acc + int(bool(op.get("accepted"))), tot + 1)
    return {k: v[0] / v[1] for k, v in counts.items() if v[1]}


def _archive_diversity(history: List[Dict[str, float]]) -> int:
    return len({(round(h["err"], 4), round(h["cost"], 4)) for h in history})


def generate_report(
    snapshot_paths: Iterable[Path] | None = None,
    out_path: Path | None = None,
    csv_path: Path | None = None,
    json_path: Path | None = None,
) -> Path:
    """Create a report summarising Pareto fronts, Δperf curves and KPIs.

    Besides the HTML report, KPI data are exported to CSV and JSON for further
    analysis.
    """

    if snapshot_paths is None:
        snapshot_paths = SNAPSHOT_DIR.glob("*/snapshot.json")

    paths = list(snapshot_paths)
    snaps = [(p, json.loads(p.read_text(encoding="utf-8"))) for p in paths]
    named_snaps = [
        (p.parent.name if p.name == "snapshot.json" else p.stem, s) for p, s in snaps
    ]

    points = [
        {
            "name": name,
            "err": snap["history"][-1]["err"],
            "cost": snap["history"][-1]["cost"],
        }
        for name, snap in named_snaps
    ]
    front = _pareto_front(points)

    records: List[Dict[str, Any]] = []
    final_errs: List[float] = []
    for name, snap in named_snaps:
        history = snap["history"]
        deltas = _delta_perf(history)
        final_errs.append(history[-1]["err"])
        records.append(
            {
                "name": name,
                "median_delta_perf": statistics.median(deltas) if deltas else 0.0,
                "acceptance": _acceptance_rates(snap.get("operations")),
                "tech_debt": history[-1]["cost"],
                "archive_diversity": _archive_diversity(history),
                "final_err": history[-1]["err"],
                "deltas": deltas,
            }
        )

    inter_run_variance = (
        statistics.pvariance(final_errs) if len(final_errs) > 1 else 0.0
    )

    html: List[str] = [
        "<html><body>",
        "<h1>Run Report</h1>",
        "<h2>Pareto Front</h2>",
        "<ul>",
    ]
    for p in front:
        html.append(f"<li>{p['name']}: err={p['err']:.4f}, cost={p['cost']:.4f}</li>")
    html.append("</ul><h2>Δperf curves</h2>")
    for rec in records:
        html.append(f"<h3>{rec['name']}</h3><pre>{rec['deltas']}</pre>")

    html.extend(
        [
            "<h2>KPIs</h2>",
            "<p>Δ perf médiane : médiane des variations d'erreur entre étapes.</p>",
            "<p>Taux d’acceptation par opérateur : proportion d'opérations acceptées pour chaque opérateur.</p>",
            "<p>Variance inter-runs : variance des erreurs finales entre runs.</p>",
            "<p>Dette technique : valeur finale de coût.</p>",
            "<p>Diversité archive : nombre de paires (err, coût) uniques observées.</p>",
            "<table><tr><th>Run</th><th>Δ perf médiane</th><th>Dette technique</th><th>Diversité</th></tr>",
        ]
    )
    for rec in records:
        html.append(
            f"<tr><td>{rec['name']}</td><td>{rec['median_delta_perf']:.4f}</td>"
            f"<td>{rec['tech_debt']:.4f}</td><td>{rec['archive_diversity']}</td></tr>"
        )
    html.append("</table>")
    for rec in records:
        if rec["acceptance"]:
            html.append(f"<h4>{rec['name']} – Taux d'acceptation</h4><ul>")
            for op, rate in rec["acceptance"].items():
                html.append(f"<li>{op}: {rate:.2%}</li>")
            html.append("</ul>")
    if inter_run_variance:
        html.append(f"<p>Variance inter-runs: {inter_run_variance:.4f}</p>")
    html.append("</body></html>")

    if out_path is None:
        out_path = REPORT_DIR / "report.html"
    out_path.write_text("\n".join(html), encoding="utf-8")

    if csv_path is None:
        csv_path = REPORT_DIR / "report.csv"
    if json_path is None:
        json_path = REPORT_DIR / "report.json"

    # Export CSV
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        fieldnames = [
            "name",
            "median_delta_perf",
            "tech_debt",
            "archive_diversity",
            "final_err",
            "acceptance",
        ]
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for rec in records:
            row = {k: rec[k] for k in fieldnames if k != "acceptance"}
            row["acceptance"] = ";".join(
                f"{op}:{rate:.3f}" for op, rate in rec["acceptance"].items()
            )
            writer.writerow(row)

    # Export JSON
    json_path.write_text(
        json.dumps({"runs": records, "inter_run_variance": inter_run_variance}),
        encoding="utf-8",
    )

    return out_path


__all__ = ["generate_report"]
