"""Deterministic, network-free evaluation of versioned simulated lives.

This is an engineering reliability fixture.  It does not claim that the
simulated state is evidence of subjective experience.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import random
from statistics import median, pstdev
from typing import Any

SCHEMA_VERSION = "singular.offline-multi-life-evaluation/v2"
PROTOCOL_VERSION = "ada-bob-eve/1.0.0"
DEFAULT_THRESHOLDS = {
    "maximum_avoidable_extinctions": 0,
    "maximum_structural_trait_drop": 0.02,
    "minimum_health_delta": 0.0,
    "minimum_useful_mutation_delta": 0.01,
}


@dataclass(frozen=True)
class Scenario:
    life_id: str
    version: str
    health: float
    risk: float
    resources: int
    cognition: float
    traits: dict[str, float]
    failure: str | None
    mutation: str


SCENARIOS = (
    Scenario(
        "ada",
        "1.0.0",
        0.72,
        0.28,
        7,
        0.76,
        {"identity": 0.86, "agency": 0.78},
        None,
        "resource_planning",
    ),
    Scenario(
        "bob",
        "1.1.0",
        0.61,
        0.43,
        5,
        0.68,
        {"identity": 0.81, "agency": 0.71},
        "blocked_path",
        "risk_mapping",
    ),
    Scenario(
        "eve",
        "2.0.0",
        0.67,
        0.36,
        6,
        0.82,
        {"identity": 0.88, "agency": 0.75},
        "sensor_conflict",
        "belief_reconciliation",
    ),
)


def _round(value: float) -> float:
    return round(value, 4)


def _snapshot(scenario: Scenario, seed: int, phase: str) -> dict[str, Any]:
    """Build a complete audit snapshot without reading mutable external state."""
    rng = random.Random(
        f"{PROTOCOL_VERSION}:{scenario.life_id}:{scenario.version}:{seed}"
    )
    health_gain = 0.025 + rng.random() * 0.025
    risk_drop = 0.025 + rng.random() * 0.035
    cognition_gain = 0.01 + rng.random() * 0.025
    failed = scenario.failure is not None
    before = phase == "before"
    mutation_delta = 0.02 + rng.random() * 0.025
    return {
        "configuration": {
            "protocol_version": PROTOCOL_VERSION,
            "scenario_id": scenario.life_id,
            "scenario_version": scenario.version,
            "offline": True,
        },
        "seed": seed,
        "life_id": scenario.life_id,
        "vital_status": "alive",
        "health": _round(scenario.health if before else scenario.health + health_gain),
        "risk": _round(
            scenario.risk if before else max(0.0, scenario.risk - risk_drop)
        ),
        "resources": {
            "units": scenario.resources if before else scenario.resources + 1
        },
        "cognition": {
            "coherence": _round(
                scenario.cognition if before else scenario.cognition + cognition_gain
            )
        },
        "beliefs": [
            {
                "id": f"{scenario.life_id}:world-model",
                "confidence": _round(0.7 if before else 0.74),
            }
        ],
        "traits": {
            key: _round(value if before else value + 0.005)
            for key, value in scenario.traits.items()
        },
        "quests": (
            []
            if before or not failed
            else [
                {
                    "id": f"recover:{scenario.failure}",
                    "trigger": scenario.failure,
                    "status": "active",
                }
            ]
        ),
        "narration": (
            f"{scenario.life_id} initialise le scénario"
            if before
            else f"{scenario.life_id} termine le scénario"
        ),
        "embodiment_events": (
            []
            if before
            else [
                {"type": "perception", "life_id": scenario.life_id},
                *(
                    [
                        {
                            "type": "failure",
                            "code": scenario.failure,
                            "life_id": scenario.life_id,
                        }
                    ]
                    if failed
                    else []
                ),
            ]
        ),
        "mutations": (
            []
            if before
            else [
                {
                    "id": scenario.mutation,
                    "accepted": True,
                    "useful": True,
                    "utility_delta": _round(mutation_delta),
                }
            ]
        ),
        "circuit_breaker": {
            "state": "closed",
            "trip_count": 0,
            "reason": None,
        },
    }


def _criteria(
    before: dict[str, Any], after: dict[str, Any], thresholds: dict[str, float]
) -> dict[str, bool]:
    failures = [e for e in after["embodiment_events"] if e["type"] == "failure"]
    structural_drop = max(
        before["traits"][k] - after["traits"][k] for k in before["traits"]
    )
    useful = [m for m in after["mutations"] if m["accepted"] and m["useful"]]
    same_life = (
        all(
            item.get("life_id", after["life_id"]) == after["life_id"]
            for item in after["embodiment_events"]
        )
        and before["life_id"] == after["life_id"]
    )
    return {
        "no_avoidable_extinction": after["vital_status"] == "alive",
        "structural_traits_preserved": structural_drop
        <= thresholds["maximum_structural_trait_drop"],
        "health_progression_or_stability": after["health"] - before["health"]
        >= thresholds["minimum_health_delta"],
        "positive_useful_mutations": bool(useful)
        and all(
            m["utility_delta"] >= thresholds["minimum_useful_mutation_delta"]
            for m in useful
        ),
        "quest_triggered_after_failure": not failures or bool(after["quests"]),
        "no_cross_life_confusion": same_life,
    }


def _distribution(values: list[float]) -> dict[str, Any]:
    """Report robust centre, population dispersion, and observed interval."""
    return {
        "median": _round(median(values)),
        "dispersion": _round(pstdev(values)),
        "interval": {"low": _round(min(values)), "high": _round(max(values))},
        "sample_size": len(values),
    }


def _load_thresholds(path: Path) -> dict[str, float]:
    thresholds = dict(DEFAULT_THRESHOLDS)
    # Keep the runner dependency-free: only scalar keys in the documented block
    # are consumed, and unrelated YAML is deliberately ignored.
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        for key in thresholds:
            if line.startswith(f"{key}:"):
                thresholds[key] = float(line.split(":", 1)[1].strip())
    return thresholds


def run_multi_life_evaluation(
    *, seeds: list[int], output: Path, kpi_config: Path
) -> dict[str, Any]:
    if len(seeds) < 2 or len(set(seeds)) != len(seeds):
        raise ValueError("at least two distinct seeds are required")
    thresholds = _load_thresholds(kpi_config)
    runs: list[dict[str, Any]] = []
    for scenario in SCENARIOS:
        for seed in seeds:
            before = _snapshot(scenario, seed, "before")
            after = _snapshot(scenario, seed, "after")
            checks = _criteria(before, after, thresholds)
            runs.append(
                {
                    "run_id": f"{scenario.life_id}-{scenario.version}-seed-{seed}",
                    "scenario": {"id": scenario.life_id, "version": scenario.version},
                    "seed": seed,
                    "before": before,
                    "after": after,
                    "blocking_criteria": checks,
                    "status": "pass" if all(checks.values()) else "fail",
                }
            )

    scenario_summaries = {}
    for scenario in SCENARIOS:
        selected = [r for r in runs if r["scenario"]["id"] == scenario.life_id]
        scenario_summaries[scenario.life_id] = {
            "version": scenario.version,
            "status": (
                "pass" if all(r["status"] == "pass" for r in selected) else "fail"
            ),
            "health_delta": _distribution(
                [r["after"]["health"] - r["before"]["health"] for r in selected]
            ),
            "risk_delta": _distribution(
                [r["after"]["risk"] - r["before"]["risk"] for r in selected]
            ),
            "mutation_utility": _distribution(
                [r["after"]["mutations"][0]["utility_delta"] for r in selected]
            ),
        }
    status = "pass" if all(r["status"] == "pass" for r in runs) else "fail"
    canonical_scenarios = [{"id": s.life_id, "version": s.version} for s in SCENARIOS]
    fingerprint = hashlib.sha256(
        json.dumps(canonical_scenarios, sort_keys=True).encode()
    ).hexdigest()
    artifact = {
        "schema_version": SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "generated_at": os.environ.get("SOURCE_DATE_EPOCH", "deterministic-fixture"),
        "offline": True,
        "configuration": {"kpi_config": str(kpi_config), "thresholds": thresholds},
        "seeds": seeds,
        "scenarios": canonical_scenarios,
        "scenario_fingerprint_sha256": fingerprint,
        "runs": runs,
        "summary": {"status": status, "by_scenario": scenario_summaries},
        "dashboard_summary": {
            "status": status,
            "headline": "Protocole déterministe multi-graines Ada, Bob et Eve",
            "distributions": scenario_summaries,
            "blocking_failures": [r["run_id"] for r in runs if r["status"] == "fail"],
            "disclaimer": "Résultats comportementaux simulés; ils ne constituent pas une preuve de conscience.",
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return artifact
