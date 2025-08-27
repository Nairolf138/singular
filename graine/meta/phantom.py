from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Dict, List, Any

from .dsl import MetaSpec
from graine.runs.replay import SNAPSHOT_DIR


def replay(history: Iterable[Dict[str, object]]) -> bool:
    """Replay a sequence of historical meta specifications.

    Each historical entry is validated using :func:`MetaSpec.validate`. If any
    entry fails validation, a ``MetaValidationError`` propagates to the caller.
    Returns ``True`` when all entries pass validation.
    """

    for entry in history:
        spec = MetaSpec.from_dict(entry)
        spec.validate()
    return True


def replay_snapshots(k: int, directory: Path = SNAPSHOT_DIR) -> Dict[str, float]:
    """Replay ``k`` snapshots using the current meta rules.

    The function loads up to ``k`` JSON snapshots from ``directory`` sorted
    lexicographically. Each snapshot must contain a ``meta`` field describing a
    :class:`MetaSpec` and a ``history`` list with ``err`` and ``cost`` values.

    For every snapshot, the meta specification is validated. The final history
    entry is compared against the first to ensure no regression of either
    metric. If a regression is detected a ``RuntimeError`` is raised. A mapping
    containing the average ``robustness`` (err) and ``safety`` (cost) across the
    processed runs is returned.
    """

    paths = sorted(Path(directory).glob("*.json"))[:k]
    total_err = 0.0
    total_cost = 0.0

    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        spec_dict: Dict[str, Any] = data.get("meta", {})
        spec = MetaSpec.from_dict(spec_dict)
        spec.validate()

        history: List[Dict[str, float]] = list(data.get("history", []))
        if not history:
            continue
        first = history[0]
        last = history[-1]
        if last.get("err", 0.0) > first.get("err", 0.0) or last.get("cost", 0.0) > first.get("cost", 0.0):
            raise RuntimeError("Regression detected")
        total_err += float(last.get("err", 0.0))
        total_cost += float(last.get("cost", 0.0))

    n = len(paths)
    return {
        "robustness": total_err / n if n else 0.0,
        "safety": total_cost / n if n else 0.0,
    }


__all__ = ["replay", "replay_snapshots"]
