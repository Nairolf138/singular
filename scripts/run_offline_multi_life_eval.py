#!/usr/bin/env python3
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from singular.evaluation import run_multi_life_evaluation  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the deterministic, versioned Ada/Bob/Eve protocol (no network)."
    )
    parser.add_argument("--seeds", default="11,23,37,53,71")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/evaluations/offline_multi_life_v2.json"),
    )
    parser.add_argument(
        "--kpi-config", type=Path, default=Path("configs/agi_kpis.yaml")
    )
    args = parser.parse_args()
    result = run_multi_life_evaluation(
        seeds=[int(x) for x in args.seeds.split(",")],
        output=args.output,
        kpi_config=args.kpi_config,
    )
    print(json.dumps(result["dashboard_summary"], ensure_ascii=False, indent=2))
    return 0 if result["dashboard_summary"]["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
