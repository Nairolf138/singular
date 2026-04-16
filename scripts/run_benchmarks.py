#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from singular.benchmarks import BenchmarkRegressionError, run_benchmarks


def main() -> int:
    parser = argparse.ArgumentParser(description="Run benchmark suites and emit artifacts.")
    parser.add_argument("--benchmarks-dir", default="benchmarks", help="Benchmark definitions directory.")
    parser.add_argument("--artifacts-dir", default="artifacts/benchmarks", help="Benchmark artifacts directory.")
    parser.add_argument("--summary-path", default="mem/benchmark_summary.json", help="Consolidated summary JSON path.")
    parser.add_argument("--weights-path", default="benchmarks/weights.json", help="Domain weights JSON path.")
    parser.add_argument(
        "--max-regression-drop",
        type=float,
        default=0.05,
        help="Fail when global score drop exceeds this threshold.",
    )
    args = parser.parse_args()

    try:
        result = run_benchmarks(
            benchmarks_dir=Path(args.benchmarks_dir),
            artifacts_dir=Path(args.artifacts_dir),
            summary_path=Path(args.summary_path),
            weights_path=Path(args.weights_path),
            max_regression_drop=args.max_regression_drop,
        )
    except BenchmarkRegressionError as exc:
        print(str(exc))
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
