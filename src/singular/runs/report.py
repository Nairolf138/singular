"""Utilities for summarizing run performance."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
import json
from typing import Any

from .logger import RUNS_DIR
from ..governance.policy import load_runtime_policy
from ..life.health import detect_health_state
from ..memory import read_skills, get_skills_file
from ..sensors import compute_host_metrics_aggregates, summarize_environmental_impact


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
                    records.append(
                        {
                            **payload,
                            "_event_type": event.get("event_type"),
                            "_ts": event.get("ts"),
                        }
                    )
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


def _build_report_payload(
    run_id: str,
    records: list[dict[str, Any]],
    *,
    skills_path: Path | str | None,
) -> dict[str, Any]:
    """Build a stable export payload for a run."""

    mutations = [
        r for r in records if r.get("_event_type") == "mutation" or "op" in r
    ]
    if not mutations:
        raise ValueError("no_mutations")

    scores = [float(r.get("score_new", 0.0)) for r in mutations]
    ops = [str(r.get("op", "?")) for r in mutations]
    counter = Counter(ops)
    first_base = float(mutations[0].get("score_base", scores[0]))
    final_score = scores[-1]

    health_scores = [
        float(h["score"])
        for r in mutations
        for h in [r.get("health", {})]
        if isinstance(h, dict) and isinstance(h.get("score"), (int, float))
    ]

    timeline: list[dict[str, Any]] = []
    for idx, mutation in enumerate(mutations, start=1):
        score_base = float(mutation.get("score_base", mutation.get("score_new", 0.0)))
        score_new = float(mutation.get("score_new", 0.0))
        delta = round(score_new - score_base, 6)
        if delta < 0:
            verdict = "improvement"
        elif delta > 0:
            verdict = "degradation"
        else:
            verdict = "stable"
        timeline.append(
            {
                "index": idx,
                "timestamp": mutation.get("_ts"),
                "operator": mutation.get("op", "?"),
                "score_base": score_base,
                "score_new": score_new,
                "delta": delta,
                "verdict": verdict,
                "decision_reason": mutation.get("decision_reason"),
            }
        )

    improvements = sum(1 for entry in timeline if entry["verdict"] == "improvement")
    degradations = sum(1 for entry in timeline if entry["verdict"] == "degradation")

    if final_score < first_base:
        final_verdict = "improvement"
    elif final_score > first_base:
        final_verdict = "degradation"
    else:
        final_verdict = "stable"

    health_payload: dict[str, Any] | None = None
    if health_scores:
        health_state = detect_health_state(health_scores, short_window=10, long_window=50)
        health_payload = {
            "score": round(health_scores[-1], 2),
            "trend": health_state,
            "window": "10/50",
        }

    alerts: list[str] = []
    if degradations > improvements:
        alerts.append("regressions_majoritaires")
    if health_payload and health_payload["trend"] in {"declining", "critical"}:
        alerts.append("sante_en_baisse")

    if skills_path is None:
        skills_path = get_skills_file()
    policy = load_runtime_policy()
    host_aggregates = compute_host_metrics_aggregates()
    host_impact = summarize_environmental_impact(host_aggregates)

    return {
        "schema_version": 1,
        "context": {
            "run_id": run_id,
            "started_at": timeline[0].get("timestamp"),
            "ended_at": timeline[-1].get("timestamp"),
            "events_count": len(records),
            "mutations_count": len(mutations),
        },
        "summary": {
            "best_score": min(scores),
            "final_score": final_score,
            "generations": len(scores),
            "operator_histogram": dict(sorted(counter.items())),
            "improvements": improvements,
            "degradations": degradations,
        },
        "timeline": timeline,
        "health": health_payload,
        "alerts": alerts,
        "verdict": final_verdict,
        "skills": read_skills(path=skills_path),
        "policy": {
            "active": policy.to_payload(),
            "impact": policy.impact_summary(),
        },
        "host_environment": {
            "aggregates": host_aggregates,
            "impact": host_impact,
        },
    }


def _render_markdown(payload: dict[str, Any]) -> str:
    """Render report payload as markdown."""

    context = payload["context"]
    summary = payload["summary"]
    lines = [
        f"# Run report `{context['run_id']}`",
        "",
        "## Contexte",
        f"- Début: {context['started_at']}",
        f"- Fin: {context['ended_at']}",
        f"- Événements: {context['events_count']}",
        f"- Mutations: {context['mutations_count']}",
        "",
        "## Résumé global",
        f"- Générations: {summary['generations']}",
        f"- Score final: {summary['final_score']}",
        f"- Meilleur score: {summary['best_score']}",
        f"- Améliorations: {summary['improvements']}",
        f"- Dégradations: {summary['degradations']}",
        f"- Verdict final: **{payload['verdict']}**",
        "",
        "## Timeline des mutations",
        "| # | ts | op | base | new | Δ | verdict |",
        "|---|----|----|------|-----|---|---------|",
    ]
    for item in payload["timeline"]:
        lines.append(
            "| {index} | {timestamp} | {operator} | {score_base} | {score_new} | {delta} | {verdict} |".format(
                **item
            )
        )

    lines.extend(["", "## Alertes"])
    alerts = payload.get("alerts", [])
    if alerts:
        lines.extend([f"- {alert}" for alert in alerts])
    else:
        lines.append("- aucune")

    lines.extend(["", "## Health score"])
    health = payload.get("health")
    if health:
        lines.append(
            f"- {health['score']}/100 ({health['trend']}, fenêtres {health['window']})"
        )
    else:
        lines.append("- indisponible")

    lines.extend(["", "## Politiques actives"])
    for item in payload.get("policy", {}).get("impact", []):
        lines.append(f"- {item}")
    lines.extend(["", "## Environnement hôte"])
    host_impact = payload.get("host_environment", {}).get("impact", {})
    lines.append(f"- Niveau d'impact: {host_impact.get('impact_level', 'low')}")
    lines.append(f"- Biais décisionnel: {host_impact.get('decision_bias', 'balanced')}")

    return "\n".join(lines) + "\n"


def report(
    run_id: str,
    *,
    runs_dir: Path | str = RUNS_DIR,
    skills_path: Path | str | None = None,
    output_format: str = "plain",
    export: str | None = None,
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

    try:
        payload = _build_report_payload(run_id, records, skills_path=skills_path)
    except ValueError:
        print(f"No mutation records for id {run_id}")
        return

    if export:
        markdown = _render_markdown(payload)
        if export == "markdown":
            print(markdown, end="")
            return
        export_path = Path(export)
        export_path.parent.mkdir(parents=True, exist_ok=True)
        if export_path.suffix.lower() == ".json":
            export_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        else:
            export_path.write_text(markdown, encoding="utf-8")
        print(f"Export written: {export_path}")
        return

    if output_format == "json":
        print(json.dumps(payload, ensure_ascii=False))
        return

    summary = payload["summary"]
    print(f"Run {run_id}")
    print(f"Generations: {summary['generations']}")
    print(f"Final score: {summary['final_score']}")
    print(f"Best score: {summary['best_score']}")

    if payload["health"]:
        print(
            "Health: "
            f"{payload['health']['score']:.2f}/100 "
            f"({payload['health']['trend']}, comparaison fenêtres {payload['health']['window']})"
        )
    host_impact = payload.get("host_environment", {}).get("impact", {})
    print(
        "Impact environnement hôte: "
        f"{host_impact.get('impact_level', 'low')} "
        f"(biais: {host_impact.get('decision_bias', 'balanced')})"
    )

    counter = summary["operator_histogram"]
    if output_format == "table":
        print("Operator histogram:")
        for op, count in sorted(counter.items()):
            print(f"{op:<24} {count:>4}")
    else:
        print("Operator histogram:")
        for op, count in counter.items():
            print(f"  {op}: {count}")

    mutations = [
        r for r in records if r.get("_event_type") == "mutation" or "op" in r
    ]
    _print_loop_modifications(mutations)

    skills = payload.get("skills", {})
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
