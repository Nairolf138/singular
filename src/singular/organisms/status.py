"""Status command implementation."""

from __future__ import annotations

import json
from pathlib import Path

from ..psyche import Psyche
from ..runs.logger import RUNS_DIR


def status(seed: int | None = None) -> None:
    """Display basic metrics and current psyche state."""

    del seed  # unused

    runs_dir = Path(RUNS_DIR)
    files = sorted(runs_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime)
    if files:
        latest = files[-1]
        records = []
        with latest.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        if records:
            last = records[-1]
            ms_new = last.get("ms_new")
            ok_count = sum(1 for r in records if r.get("ok"))
            success_rate = ok_count / len(records) * 100
            print(f"Latest run: {latest.stem}")
            if isinstance(ms_new, (int, float)):
                print(f"Last execution speed: {ms_new:.2f}ms")
            print(f"Success rate: {success_rate:.0f}%")
        else:
            print(f"Run log {latest.name} is empty.")
    else:
        print("No run logs found.")

    psyche = Psyche.load_state()
    mood = psyche.last_mood or "neutral"
    print(f"Mood: {mood}")
    print("Traits:")
    print(f"  curiosity: {psyche.curiosity:.2f}")
    print(f"  patience: {psyche.patience:.2f}")
    print(f"  playfulness: {psyche.playfulness:.2f}")
