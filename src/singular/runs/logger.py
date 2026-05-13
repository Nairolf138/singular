"""Utilities for recording execution runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import json
import logging
import os
from typing import Any, Mapping

from ..storage_retention import run_retention_service

from ..psyche import Psyche
from ..memory import add_episode, add_procedural_memory
from typing import Callable, Dict

# Base directory for persistent files
_BASE_DIR = Path(os.environ.get("SINGULAR_HOME", "."))
# Directory where run logs are stored
RUNS_DIR = _BASE_DIR / "runs"
EVENT_SCHEMA_VERSION = 1
USAGE_REPUTATION_SCHEMA_VERSION = 1
DEFAULT_REPUTATION_UPDATE_EVERY = int(os.environ.get("SINGULAR_REPUTATION_UPDATE_EVERY", "5"))

# ---------------------------------------------------------------------------
# Mood style helpers
# ---------------------------------------------------------------------------


def _style_colere(mood: str) -> str:
    """Rendering for the ``colere`` (anger) mood."""

    return mood.upper()


def _style_fatigue(mood: str) -> str:
    """Rendering for the ``fatigue`` (tired) mood."""

    return f"{mood}..."


def _style_neutre(mood: str) -> str:
    """Rendering for the ``neutre`` (neutral) mood."""

    return mood


mood_styles: Dict[str | None, Callable[[str], str]] = {
    "colere": _style_colere,
    "colère": _style_colere,
    "fatigue": _style_fatigue,
    "neutre": _style_neutre,
    None: _style_neutre,
}

_provider_logger = logging.getLogger("singular.provider")


def log_provider_event(
    *,
    provider: str,
    latency_ms: float,
    fallback: bool,
    error_category: str | None,
) -> None:
    """Emit a structured provider log entry."""

    payload = {
        "event": "provider_call",
        "provider": provider,
        "latency_ms": round(latency_ms, 2),
        "fallback": fallback,
        "error_category": error_category,
    }
    _provider_logger.info("provider_call", extra={"payload": payload})


def _ensure_dir(path: Path) -> None:
    """Ensure ``path``'s parent directory exists."""
    path.parent.mkdir(parents=True, exist_ok=True)


def _enforce_retention(root: Path) -> None:
    """Apply retention policy to run logs and temporary files."""

    run_retention_service(base_dir=_BASE_DIR, runs_dir=root)


@dataclass
class RunLogger:
    """Append JSONL run records with crash recovery.

    Parameters
    ----------
    run_id:
        Identifier for the run.
    root:
        Directory in which log files are written. Defaults to :data:`RUNS_DIR`.
    """

    run_id: str
    root: Path = RUNS_DIR
    psyche: Psyche = field(default_factory=Psyche.load_state)
    reputation_update_every: int = DEFAULT_REPUTATION_UPDATE_EVERY

    def __post_init__(self) -> None:
        self.root = Path(self.root)
        self.root.mkdir(parents=True, exist_ok=True)

        self.run_dir = self.root / self.run_id
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self._active_lock_path = self.run_dir / ".active.lock"
        self._active_lock_path.write_text(
            json.dumps({"run_id": self.run_id, "started_at": datetime.utcnow().isoformat(timespec="seconds")}),
            encoding="utf-8",
        )
        self.events_path = self.run_dir / "events.jsonl"
        self._events_file = self.events_path.open("a", encoding="utf-8")
        self.consciousness_path = self.run_dir / "consciousness.jsonl"
        self._consciousness_file = self.consciousness_path.open("a", encoding="utf-8")
        self.skill_reputation_path = self.run_dir / "skill_reputation.json"
        self._skill_telemetry: dict[str, dict[str, float | int]] = {}
        self._skill_reputation: dict[str, dict[str, float | int]] = {}
        self._load_skill_reputation()

        # Resume from existing temporary file if present
        tmp_pattern = f"{self.run_id}-*.jsonl.tmp"
        existing = sorted(self.root.glob(tmp_pattern))
        if existing:
            self.tmp_path = existing[-1]
            # derive final path and timestamp from tmp file name
            self.path = self.tmp_path.with_suffix("")
            stem = self.path.name
            # stem is <id>-<timestamp>
            self.timestamp = stem.split("-", 1)[1]
            self._file = self.tmp_path.open("a", encoding="utf-8")
        else:
            self.timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
            self.path = self.root / f"{self.run_id}-{self.timestamp}.jsonl"
            self.tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
            _ensure_dir(self.tmp_path)
            self._file = self.tmp_path.open("a", encoding="utf-8")

    def _load_skill_reputation(self) -> None:
        if not self.skill_reputation_path.exists():
            return
        try:
            payload = json.loads(self.skill_reputation_path.read_text(encoding="utf-8"))
        except (OSError, TypeError, json.JSONDecodeError):
            return
        if not isinstance(payload, Mapping):
            return
        skills = payload.get("skills")
        if isinstance(skills, Mapping):
            for skill_name, raw in skills.items():
                if isinstance(raw, Mapping):
                    self._skill_reputation[str(skill_name)] = {
                        "success_rate": float(raw.get("success_rate", 0.0)),
                        "mean_cost": float(raw.get("mean_cost", 0.0)),
                        "recent_failures": int(raw.get("recent_failures", 0)),
                        "mean_quality": float(raw.get("mean_quality", 0.0)),
                        "mean_satisfaction": float(raw.get("mean_satisfaction", 0.0)),
                        "use_count": int(raw.get("use_count", 0)),
                    }

    def _append_skill_telemetry(
        self,
        *,
        skill: str,
        success: bool,
        latency_ms: float,
        resource_cost: float,
        perceived_quality: float,
        user_satisfaction: float,
    ) -> None:
        telemetry = self._skill_telemetry.setdefault(
            skill,
            {
                "count": 0,
                "successes": 0,
                "total_latency_ms": 0.0,
                "total_resource_cost": 0.0,
                "total_quality": 0.0,
                "total_satisfaction": 0.0,
                "recent_failures": 0,
            },
        )
        telemetry["count"] = int(telemetry["count"]) + 1
        telemetry["successes"] = int(telemetry["successes"]) + int(bool(success))
        telemetry["total_latency_ms"] = float(telemetry["total_latency_ms"]) + float(latency_ms)
        telemetry["total_resource_cost"] = float(telemetry["total_resource_cost"]) + float(resource_cost)
        telemetry["total_quality"] = float(telemetry["total_quality"]) + float(perceived_quality)
        telemetry["total_satisfaction"] = float(telemetry["total_satisfaction"]) + float(user_satisfaction)
        telemetry["recent_failures"] = (
            0 if success else min(int(telemetry["recent_failures"]) + 1, 1000)
        )

    def _maybe_update_skill_reputation(self, *, force: bool = False) -> None:
        pending = sum(int(skill_data.get("count", 0)) for skill_data in self._skill_telemetry.values())
        threshold = max(1, int(self.reputation_update_every))
        if not force and pending < threshold:
            return
        if pending <= 0:
            return

        for skill_name, telemetry in self._skill_telemetry.items():
            count = max(1, int(telemetry.get("count", 0)))
            success_rate = float(telemetry.get("successes", 0)) / count
            mean_cost = float(telemetry.get("total_resource_cost", 0.0)) / count
            recent_failures = int(telemetry.get("recent_failures", 0))
            mean_quality = float(telemetry.get("total_quality", 0.0)) / count
            mean_satisfaction = float(telemetry.get("total_satisfaction", 0.0)) / count

            previous = self._skill_reputation.get(skill_name, {})
            previous_count = int(previous.get("use_count", 0))
            blend = 0.0 if previous_count <= 0 else min(0.8, previous_count / (previous_count + count))
            self._skill_reputation[skill_name] = {
                "success_rate": (float(previous.get("success_rate", success_rate)) * blend)
                + (success_rate * (1.0 - blend)),
                "mean_cost": (float(previous.get("mean_cost", mean_cost)) * blend)
                + (mean_cost * (1.0 - blend)),
                "recent_failures": recent_failures,
                "mean_quality": (float(previous.get("mean_quality", mean_quality)) * blend)
                + (mean_quality * (1.0 - blend)),
                "mean_satisfaction": (float(previous.get("mean_satisfaction", mean_satisfaction)) * blend)
                + (mean_satisfaction * (1.0 - blend)),
                "use_count": previous_count + count,
            }

        payload = {
            "version": USAGE_REPUTATION_SCHEMA_VERSION,
            "updated_at": datetime.utcnow().isoformat(timespec="seconds"),
            "skills": self._skill_reputation,
        }
        self.skill_reputation_path.write_text(json.dumps(payload), encoding="utf-8")
        self._skill_telemetry.clear()

    def skill_reputation(self) -> dict[str, dict[str, float | int]]:
        return {name: dict(stats) for name, stats in self._skill_reputation.items()}

    def _write_record(self, record: dict[str, Any]) -> None:
        self._file.write(json.dumps(record) + "\n")
        self._file.flush()
        os.fsync(self._file.fileno())

    def _write_event(self, event_type: str, payload: dict[str, Any], ts: str) -> None:
        event = {
            "version": EVENT_SCHEMA_VERSION,
            "event_type": event_type,
            "ts": ts,
            "payload": payload,
        }
        self._events_file.write(json.dumps(event) + "\n")
        self._events_file.flush()
        os.fsync(self._events_file.fileno())

    def log_consciousness(
        self,
        *,
        perception_summary: str,
        evaluated_hypotheses: list[dict[str, Any]],
        final_choice: str | None,
        justification: str,
        objective: str | None = None,
        mood: str | None = None,
        energy: float | None = None,
        success: bool | None = None,
    ) -> None:
        """Record a reflection event in ``runs/<run_id>/consciousness.jsonl``."""

        ts = datetime.utcnow().isoformat(timespec="seconds")
        record: dict[str, Any] = {
            "ts": ts,
            "event": "consciousness",
            "perception_summary": perception_summary,
            "evaluated_hypotheses": evaluated_hypotheses,
            "final_choice": final_choice,
            "justification": justification,
            "objective": objective,
            "emotional_state": {
                "mood": mood,
                "energy": energy,
            },
            "success": success,
        }
        self._consciousness_file.write(json.dumps(record) + "\n")
        self._consciousness_file.flush()
        os.fsync(self._consciousness_file.fileno())

    def log(
        self,
        skill: str,
        op: str,
        diff: str,
        ok: bool,
        ms_base: float,
        ms_new: float,
        score_base: float,
        score_new: float,
        *,
        impacted_file: str | None = None,
        decision_reason: str | None = None,
        alternative_scores: list[tuple[int, str, float]] | None = None,
        human_summary: str | None = None,
        loop_modifications: dict[str, int] | None = None,
        health: dict[str, float | int] | None = None,
        usage_metrics: Mapping[str, float | bool] | None = None,
        source_error_type: str | None = None,
        source_error_message: str | None = None,
        mutation_error_type: str | None = None,
        mutation_error_message: str | None = None,
    ) -> None:
        """Append a mutation record to the log file."""

        ts = datetime.utcnow().isoformat(timespec="seconds")
        record: dict[str, Any] = {
            "ts": ts,
            "skill": skill,
            "op": op,
            "diff": diff,
            "ok": ok,
            "ms_base": ms_base,
            "ms_new": ms_new,
            "score_base": score_base,
            "score_new": score_new,
            "improved": score_new < score_base,
            "impacted_file": impacted_file,
            "decision_reason": decision_reason,
            "alternative_scores": alternative_scores or [],
            "human_summary": human_summary,
            "loop_modifications": loop_modifications or {},
            "health": health or {},
            "usage_metrics": dict(usage_metrics or {}),
            "source_error_type": source_error_type,
            "source_error_message": source_error_message,
            "mutation_error_type": mutation_error_type,
            "mutation_error_message": mutation_error_message,
        }
        self._write_record(record)
        self._write_event("mutation", record, ts)
        if usage_metrics:
            self._append_skill_telemetry(
                skill=skill,
                success=bool(usage_metrics.get("success", ok)),
                latency_ms=float(usage_metrics.get("latency_ms", ms_new)),
                resource_cost=float(usage_metrics.get("resource_cost", 0.0)),
                perceived_quality=float(usage_metrics.get("perceived_quality", 0.0)),
                user_satisfaction=float(usage_metrics.get("user_satisfaction", 0.0)),
            )
            self._maybe_update_skill_reputation()

        self.psyche.process_run_record(record)
        mood = getattr(self.psyche, "last_mood", None)
        mood_val = getattr(mood, "value", mood)
        add_episode(
            {"event": "mutation", "mood": mood_val, **record}, mood_styles=mood_styles
        )
        add_procedural_memory(record)


    def log_phase_metrics(
        self,
        *,
        iteration: int | None,
        phases: Mapping[str, object],
        total_ms: float,
        slowest_phase: str | None = None,
        cache_candidates: list[dict[str, object]] | None = None,
        async_distribution_note: str | None = None,
    ) -> None:
        """Record life-loop phase timings for profiling and dashboard views."""

        record: dict[str, Any] = {
            "ts": datetime.utcnow().isoformat(timespec="seconds"),
            "event": "life_loop_phase_metrics",
            "iteration": iteration,
            "phase_metrics": {
                "schema_version": 1,
                "total_ms": total_ms,
                "slowest_phase": slowest_phase,
                "phases": dict(phases),
                "cache_candidates": cache_candidates or [],
                "async_distribution_note": async_distribution_note,
            },
        }
        self._write_record(record)
        self._write_event("life_loop_phase_metrics", record, record["ts"])

    def log_death(self, reason: str, **info: Any) -> None:
        """Record a death event with optional additional information."""

        record: dict[str, Any] = {
            "ts": datetime.utcnow().isoformat(timespec="seconds"),
            "event": "death",
            "reason": reason,
            **info,
        }
        self._write_record(record)
        self._write_event("death", record, record["ts"])
        add_episode(record)

    def log_refusal(self, skill: str) -> None:
        """Record a refusal to mutate ``skill``."""

        record: dict[str, Any] = {
            "ts": datetime.utcnow().isoformat(timespec="seconds"),
            "event": "refuse",
            "skill": skill,
        }
        self._write_record(record)
        self._write_event("refuse", record, record["ts"])
        add_episode(record)

    def log_delay(self, skill: str, resume_at: float) -> None:
        """Record a procrastination event for ``skill``."""

        record: dict[str, Any] = {
            "ts": datetime.utcnow().isoformat(timespec="seconds"),
            "event": "delay",
            "skill": skill,
            "resume_at": resume_at,
        }
        self._write_record(record)
        self._write_event("delay", record, record["ts"])
        add_episode(record)

    def log_absurde(self, skill: str, diff: str) -> None:
        """Record an absurd mutation event."""

        record: dict[str, Any] = {
            "ts": datetime.utcnow().isoformat(timespec="seconds"),
            "event": "absurde",
            "skill": skill,
            "diff": diff,
        }
        self._write_record(record)
        self._write_event("absurde", record, record["ts"])
        add_episode(record)

    def log_interaction(self, event: str, **info: Any) -> None:
        """Record an explicit ecosystem interaction event."""

        record: dict[str, Any] = {
            "ts": datetime.utcnow().isoformat(timespec="seconds"),
            "event": "interaction",
            "interaction": event,
            **info,
        }
        self._write_record(record)
        self._write_event("interaction", record, record["ts"])
        add_episode(record)

    def log_event(self, event: str, **info: Any) -> None:
        """Record a named run event without wrapping it as an interaction."""

        record: dict[str, Any] = {
            "ts": datetime.utcnow().isoformat(timespec="seconds"),
            "event": event,
            **info,
        }
        self._write_record(record)
        self._write_event(event, record, record["ts"])
        add_episode(record)

    def log_test_coevolution(
        self,
        *,
        skill: str,
        accepted: bool,
        pool_size: int,
        added: int,
        removed: int,
        detection_rate: float,
        score_base: float,
        score_new: float,
        score_combined_base: float,
        score_combined_new: float,
        robustness_score: float | None = None,
        proposed_tests: list[str] | None = None,
        retained_tests: list[str] | None = None,
        rejected_tests: list[str] | None = None,
        rejected_for_robustness: bool = False,
    ) -> None:
        """Record co-evolution decisions for the living test pool."""

        record: dict[str, Any] = {
            "ts": datetime.utcnow().isoformat(timespec="seconds"),
            "event": "test_coevolution",
            "skill": skill,
            "accepted": accepted,
            "pool_size": pool_size,
            "tests_added": added,
            "tests_removed": removed,
            "regression_detection_rate": detection_rate,
            "score_base": score_base,
            "score_new": score_new,
            "score_combined_base": score_combined_base,
            "score_combined_new": score_combined_new,
            "robustness_score": robustness_score,
            "tests_proposed": proposed_tests or [],
            "tests_retained": retained_tests or [],
            "tests_rejected": rejected_tests or [],
            "mutation_rejected_for_robustness": rejected_for_robustness,
        }
        self._write_record(record)
        self._write_event("test_coevolution", record, record["ts"])
        add_episode(record)

    def close(self) -> None:
        """Flush and finalize the log files atomically."""
        if not self._consciousness_file.closed:
            self._consciousness_file.flush()
            os.fsync(self._consciousness_file.fileno())
            self._consciousness_file.close()
        if not self._events_file.closed:
            self._events_file.flush()
            os.fsync(self._events_file.fileno())
            self._events_file.close()
        if not self._file.closed:
            self._maybe_update_skill_reputation(force=True)
            self._file.flush()
            os.fsync(self._file.fileno())
            self._file.close()
            os.replace(self.tmp_path, self.path)
            try:
                self._active_lock_path.unlink()
            except FileNotFoundError:
                pass
            _enforce_retention(self.root)

    def __enter__(self) -> RunLogger:  # pragma: no cover - trivial
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # pragma: no cover - trivial
        self.close()
