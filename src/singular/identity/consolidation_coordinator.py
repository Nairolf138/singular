"""Restartable, audit-preserving consolidation of the higher memory layers."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Callable

from ..io_utils import atomic_write_text


STAGES = (
    "semantic_memory",
    "autobiographical_memory",
    "metacognitive_self_model",
    "models_of_others",
    "probabilistic_beliefs",
    "imitation_learning",
    "narrative_projection",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _key(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


class ConsolidationCoordinator:
    """Run independently checkpointed projections after episodic consolidation.

    The catalogue is deliberately distinct from the projections.  It is the audit
    ledger: retention may demote or forget content, but never its provenance.
    """

    def __init__(self, mem_dir: Path | str) -> None:
        self.mem_dir = Path(mem_dir)
        self.mem_dir.mkdir(parents=True, exist_ok=True)
        self.state_path = self.mem_dir / "consolidation_coordinator.json"
        self.catalogue_path = self.mem_dir / "consolidation_audit.json"

    def _read(self, path: Path, default: Any) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return default

    def _write(self, path: Path, value: Any) -> None:
        atomic_write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")

    def _state(self) -> dict[str, Any]:
        value = self._read(self.state_path, {})
        if not isinstance(value, dict):
            value = {}
        value.setdefault("version", 1)
        value.setdefault("stages", {})
        return value

    @staticmethod
    def _stage_items(stage: str, episodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        keys = {
            "semantic_memory": ("user_fact", "preference", "constraint", "fact"),
            "autobiographical_memory": ("user_fact", "autobiographical_fact", "achievement", "failure"),
            "metacognitive_self_model": ("strategy", "error", "bias", "failure_condition"),
            "models_of_others": ("individual_id", "other_id", "person"),
            "probabilistic_beliefs": ("belief", "hypothesis", "success", "reward"),
            "imitation_learning": ("demonstration", "observations", "actions", "skill"),
            "narrative_projection": ("narrative", "heading", "achievement", "failure"),
        }[stage]
        return [episode for episode in episodes if any(key in episode for key in keys)]

    def _apply_stage(self, stage: str, episodes: list[dict[str, Any]]) -> dict[str, int]:
        catalogue = self._read(self.catalogue_path, {})
        if not isinstance(catalogue, dict):
            catalogue = {}
        counts = {key: 0 for key in ("seen", "reinforced", "merged", "demoted", "forgotten", "rejected")}
        items = self._stage_items(stage, episodes)
        counts["seen"] = len(items)
        now = _now()
        for episode in items:
            provenance = str(episode.get("id") or episode.get("event_id") or _key(episode))
            content = next(
                (episode[key] for key in (
                    "value", "user_fact", "autobiographical_fact", "preference",
                    "constraint", "belief", "hypothesis", "narrative", "heading",
                    "strategy", "error", "bias", "skill", "individual_id",
                    "other_id", "person",
                ) if episode.get(key) is not None),
                episode,
            )
            normalized = str(content).strip().casefold()
            item_id = _key([stage, normalized])
            critical = bool(episode.get("critical") or episode.get("importance") in {"critical", "high"})
            existing = catalogue.get(item_id)
            if isinstance(existing, dict):
                if provenance in existing.get("provenance", []):
                    counts["merged"] += 1
                    continue
                existing.setdefault("provenance", []).append(provenance)
                existing["mentions"] = int(existing.get("mentions", 1)) + 1
                existing["last_seen"] = str(episode.get("ts") or now)
                existing["status"] = "active"
                counts["reinforced"] += 1
            else:
                opposite = normalized.removeprefix("not ") if normalized.startswith("not ") else "not " + normalized
                contradictions = [
                    key for key, row in catalogue.items()
                    if isinstance(row, dict) and row.get("stage") == stage and row.get("normalized") == opposite
                ]
                rejected = False
                for conflict_id in contradictions:
                    conflict = catalogue[conflict_id]
                    conflict.setdefault("contradicted_by", []).append(item_id)
                    if conflict.get("critical"):
                        rejected = True
                    else:
                        conflict["status"] = "demoted"
                        counts["demoted"] += 1
                catalogue[item_id] = {
                    "stage": stage, "content": content, "normalized": normalized,
                    "provenance": [provenance], "mentions": 1, "critical": critical,
                    "status": "rejected" if rejected else "active",
                    "obsolete": bool(episode.get("obsolete")),
                    "first_seen": str(episode.get("ts") or now),
                    "last_seen": str(episode.get("ts") or now), "contradicts": contradictions,
                }
                counts["rejected"] += int(rejected)
        # Obsolete evidence can leave active memory, but critical records and the
        # audit entry itself are immutable retention invariants.
        for row in catalogue.values():
            if not isinstance(row, dict) or row.get("stage") != stage or row.get("critical"):
                continue
            if row.get("obsolete") and row.get("status") != "forgotten":
                row["status"] = "forgotten"
                counts["forgotten"] += 1
        self._write(self.catalogue_path, catalogue)
        projection = [row for row in catalogue.values() if isinstance(row, dict) and row.get("stage") == stage and row.get("status") not in {"forgotten", "rejected"}]
        self._write(self.mem_dir / f"consolidated_{stage}.json", projection)
        return counts

    def run(
        self,
        episodes: list[dict[str, Any]],
        *,
        after_stage: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        """Run all stages, resuming after the last committed stage on interruption."""
        state = self._state()
        # Keep the input beside the checkpoints until every projection commits.
        # The episodic journal may already have been compacted by the base pass.
        if episodes:
            state["pending_episodes"] = episodes
            self._write(self.state_path, state)
        elif isinstance(state.get("pending_episodes"), list):
            episodes = [row for row in state["pending_episodes"] if isinstance(row, dict)]
        batch = _key([_key(episode) for episode in episodes])
        totals = {key: 0 for key in ("seen", "reinforced", "merged", "demoted", "forgotten", "rejected")}
        errors: list[dict[str, str]] = []
        results: dict[str, Any] = {}
        for stage in STAGES:
            checkpoint = state["stages"].get(stage, {})
            if checkpoint.get("cursor") == batch and checkpoint.get("status") == "completed":
                result = checkpoint.get("result", {})
            else:
                try:
                    result = self._apply_stage(stage, episodes)
                    state["stages"][stage] = {"cursor": batch, "status": "completed", "result": result, "completed_at": _now()}
                    self._write(self.state_path, state)  # commit each stage separately
                    if after_stage:
                        after_stage(stage)
                except Exception as exc:  # retain earlier commits and continue
                    error = {"stage": stage, "error": f"{type(exc).__name__}: {exc}"}
                    errors.append(error)
                    state["stages"][stage] = {"cursor": batch, "status": "failed", "result": {}, **error}
                    self._write(self.state_path, state)
                    continue
            results[stage] = result
            for key in totals:
                totals[key] += int(result.get(key, 0))
        if not errors:
            state.pop("pending_episodes", None)
            self._write(self.state_path, state)
        return {
            "event_type": "sleep.consolidation.completed",
            "completed_at": _now(),
            "batch_cursor": batch,
            "items": totals,
            "items_seen": totals["seen"],
            "items_reinforced": totals["reinforced"],
            "items_merged": totals["merged"],
            "items_demoted": totals["demoted"],
            "items_forgotten": totals["forgotten"],
            "items_rejected": totals["rejected"],
            "stages": results,
            "partial_errors": errors,
        }
