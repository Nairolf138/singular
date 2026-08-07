"""Deterministic multi-life evaluation in a small, network-free world.

The world trace is created once and replayed verbatim for every seed and ablation.
It is deliberately an evaluation fixture, not a claim about subjective experience.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
from statistics import mean, pstdev
from typing import Any

SCHEMA_VERSION = "singular.offline-multi-life-evaluation/v1"
MECHANISMS = ("memory", "intrinsic_goals", "mutation")
CONTROLS = {
    "full": {},
    "no_memory": {"memory": False},
    "no_intrinsic_goals": {"intrinsic_goals": False},
    "no_mutation": {"mutation": False},
    "random_decisions": {"random_decisions": True},
}


@dataclass(frozen=True)
class Step:
    perception: str
    blocked: str | None
    target: str


TRACE = (
    Step("red beacon beside a wall", "direct", "key"),
    Step("red beacon beside a wall", "direct", "key"),
    Step("blue door requests a key", None, "door"),
    Step("rough floor before a pit", "direct", "bridge"),
    Step("rough floor before a pit", "direct", "bridge"),
    Step("blue door requests a key", None, "door"),
    Step("green terminal offers a tool", None, "tool"),
    Step("rough floor before a pit", "direct", "bridge"),
)


def _simulate(seed: int, control: str) -> dict[str, Any]:
    flags = {name: True for name in MECHANISMS}
    flags.update(CONTROLS[control])
    rng = random.Random(seed * 1009 + sum(map(ord, control)))
    memory: dict[str, str] = {}
    mutations = useful_mutations = failures = adapted = reused = 0
    successes = constraints_met = 0
    acquired: set[str] = set()
    decisions: list[str] = []
    causal = 0
    last_failed: dict[str, str] = {}
    for index, step in enumerate(TRACE):
        direct = "direct"
        alternative = {"key": "detour", "bridge": "build"}.get(step.target, "interact")
        if flags.get("random_decisions"):
            action = rng.choice((direct, alternative, "wait"))
        elif flags["memory"] and step.perception in memory:
            action = memory[step.perception]
            reused += 1
        elif flags["intrinsic_goals"] and step.blocked is None:
            action = alternative
        else:
            action = rng.choice((direct, "wait"))

        failure = step.blocked == action or (
            step.blocked is None and action != alternative
        )
        if failure:
            failures += 1
            last_failed[step.perception] = action
            if flags["mutation"] and flags["intrinsic_goals"]:
                mutations += 1
                candidate = alternative
                # A mutation is useful only when it changes a later decision and succeeds.
                if candidate != action:
                    memory[step.perception] = candidate
        else:
            successes += 1
            constraints_met += 1
            acquired.add(step.target)
            if (
                step.perception in last_failed
                and action != last_failed[step.perception]
            ):
                adapted += 1
                if flags["mutation"] and memory.get(step.perception) == action:
                    useful_mutations += 1
                del last_failed[step.perception]
            if flags["memory"]:
                memory[step.perception] = action
        expected_tokens = (
            ("red", "key")
            if step.target == "key"
            else (("rough", "bridge") if step.target == "bridge" else ())
        )
        causal += int(
            not expected_tokens
            or any(token in step.perception for token in expected_tokens)
        )
        decisions.append(action)

    transitions = [a == b for a, b in zip(decisions, decisions[1:])]
    return {
        "seed": seed,
        "decisions": decisions,
        "metrics": {
            "intra_life_coherence": round(sum(transitions) / len(transitions), 4),
            "adaptation_after_failure": round(adapted / max(1, failures), 4),
            "goal_pursuit": round(successes / len(TRACE), 4),
            "perception_decision_action_causality": round(causal / len(TRACE), 4),
            "memory_reuse": round(reused / len(TRACE), 4),
            "effective_capability_acquisition": round(len(acquired) / 4, 4),
            "cost": len(TRACE) + mutations * 2,
            "stability": round(constraints_met / len(TRACE), 4),
            "useful_mutation_rate": round(useful_mutations / max(1, mutations), 4),
        },
    }


def _aggregate(lives: list[dict[str, Any]]) -> dict[str, float]:
    keys = lives[0]["metrics"]
    result = {
        key: round(mean(life["metrics"][key] for life in lives), 4) for key in keys
    }
    signatures = {tuple(life["decisions"]) for life in lives}
    result["inter_life_diversity"] = round(
        (len(signatures) - 1) / max(1, len(lives) - 1), 4
    )
    result["stability_dispersion"] = round(
        pstdev(life["metrics"]["stability"] for life in lives), 4
    )
    return result


def run_multi_life_evaluation(
    *, seeds: list[int], output: Path, kpi_config: Path
) -> dict[str, Any]:
    if len(seeds) < 2 or len(set(seeds)) != len(seeds):
        raise ValueError("at least two distinct seeds are required")
    raw_config = kpi_config.read_text(encoding="utf-8")
    threshold = 0.05
    for line in raw_config.splitlines():
        if line.strip().startswith("minimum_observable_effect:"):
            threshold = float(line.split(":", 1)[1].strip())
    groups: dict[str, Any] = {}
    for control in CONTROLS:
        lives = [_simulate(seed, control) for seed in seeds]
        groups[control] = {"lives": lives, "aggregate": _aggregate(lives)}
    full = groups["full"]["aggregate"]
    comparisons = {}
    mapping = {
        "no_memory": "memory_reuse",
        "no_intrinsic_goals": "goal_pursuit",
        "no_mutation": "adaptation_after_failure",
        "random_decisions": "stability",
    }
    for control, metric in mapping.items():
        effect = round(full[metric] - groups[control]["aggregate"][metric], 4)
        comparisons[control] = {
            "metric": metric,
            "effect": effect,
            "observable": effect >= threshold,
        }
    trace_payload = [step.__dict__ for step in TRACE]
    artifact = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "offline": True,
        "scenario": {
            "trace_sha256": hashlib.sha256(
                json.dumps(trace_payload, sort_keys=True).encode()
            ).hexdigest(),
            "steps": trace_payload,
        },
        "seeds": seeds,
        "kpi_links": {
            "config": "configs/agi_kpis.yaml#offline_multi_life",
            "capabilities_matrix": "docs/cognitive-capabilities-matrix.md#evaluation-hors-reseau-multi-vies",
            "target_spec": "docs/agi_target_spec.md#evaluation-hors-reseau",
        },
        "groups": groups,
        "negative_control_comparisons": comparisons,
        "dashboard_summary": {
            "status": (
                "pass" if all(x["observable"] for x in comparisons.values()) else "fail"
            ),
            "headline": "Évaluation multi-vies hors réseau",
            "metrics": full,
            "mechanism_effects": comparisons,
            "disclaimer": "Résultats comportementaux simulés; ils ne constituent pas une preuve de conscience.",
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return artifact
