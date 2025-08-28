"""Visualize run performance with plots or ASCII charts."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from singular.runs.report import load_run_records


def _ascii_charts(scores: list[float], ops: list[str]) -> None:
    for idx, score in enumerate(scores, 1):
        print(f"Generation {idx}: {score}")
    print("Operator histogram:")
    counts = Counter(ops)
    for op, count in counts.items():
        print(f"{op}: {'#' * count}")


def _png_charts(scores: list[float], ops: list[str], output: Path) -> None:
    import matplotlib.pyplot as plt  # type: ignore

    counts = Counter(ops)
    fig, axes = plt.subplots(2, 1, figsize=(6, 6))
    axes[0].plot(range(1, len(scores) + 1), scores, marker="o")
    axes[0].set_xlabel("Generation")
    axes[0].set_ylabel("Score")
    axes[1].bar(list(counts.keys()), list(counts.values()))
    axes[1].set_xlabel("Operator")
    axes[1].set_ylabel("Count")
    fig.tight_layout()
    fig.savefig(output)
    plt.close(fig)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Visualize run performance")
    parser.add_argument("--id", required=True, help="Run identifier")
    parser.add_argument("--ascii", action="store_true", help="Output ASCII charts")
    parser.add_argument("--output", type=Path, help="PNG file to write")
    args = parser.parse_args(argv)

    try:
        records = load_run_records(args.id)
    except FileNotFoundError:
        print(f"No run log found for id {args.id}")
        return 1

    scores = [r.get("score_new", 0.0) for r in records]
    ops = [r.get("op", "?") for r in records]

    if args.ascii:
        _ascii_charts(scores, ops)
    else:
        try:
            output = args.output or Path(f"{args.id}.png")
            _png_charts(scores, ops, output)
            print(f"Saved plot to {output}")
        except Exception:
            print("matplotlib is required for PNG output; use --ascii if unavailable")
            return 1
    return 0


if __name__ == "__main__":  # pragma: no cover - script entry point
    raise SystemExit(main())
