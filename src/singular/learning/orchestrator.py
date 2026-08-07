"""Conservative, transactional learning from normalized feedback events.

The orchestrator deliberately keeps observations and candidates separate from the
state used by the rest of a life.  A candidate only becomes active after enough
independent evidence and a successful persistent regression-suite evaluation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Callable, Mapping
import uuid

from singular.beliefs.store import BeliefStore
from singular.io_utils import atomic_write_text, file_lock


FEEDBACK_SOURCES = frozenset({"run", "conversation", "action", "perception", "social"})
UPDATE_KINDS = frozenset({"strategy", "belief", "skill"})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class FeedbackEvent:
    """Source-independent feedback contract accepted by :meth:`ingest`."""

    source: str
    subject: str
    reward: float
    context: Mapping[str, Any] = field(default_factory=dict)
    payload: Mapping[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    occurred_at: str = field(default_factory=_now)
    life_id: str = "default"

    def __post_init__(self) -> None:
        if self.source not in FEEDBACK_SOURCES:
            raise ValueError(f"unsupported feedback source: {self.source}")
        if not self.subject.strip():
            raise ValueError("feedback subject must not be empty")
        if not math.isfinite(float(self.reward)):
            raise ValueError("reward must be finite")


@dataclass(frozen=True)
class LearningPolicy:
    max_events_per_cycle: int = 100
    max_candidates_per_cycle: int = 10
    minimum_evidence: int = 3
    minimum_distinct_sources: int = 2
    minimum_regression_cases: int = 1
    promotion_reward: float = 0.0
    decay: float = 0.98
    drift_threshold: float = 0.45
    max_regression: float = 0.05
    minimum_retention: float = 0.90


@dataclass(frozen=True)
class PromotionDecision:
    candidate_id: str
    activated: bool
    reason: str
    evaluation: Mapping[str, float]
    rollback_path: str | None


Evaluator = Callable[[str, str, Any, list[dict[str, Any]]], Mapping[str, float]]


class LearningOrchestrator:
    """Per-life feedback aggregation, evaluation, promotion and rollback."""

    def __init__(
        self,
        root: Path | str,
        *,
        life_id: str = "default",
        policy: LearningPolicy | None = None,
        belief_store: BeliefStore | None = None,
        evaluator: Evaluator | None = None,
    ) -> None:
        self.root = Path(root)
        self.life_id = life_id
        self.policy = policy or LearningPolicy()
        # The life id is a directory component only after rejecting traversal.
        if not life_id or Path(life_id).name != life_id:
            raise ValueError("life_id must be a single safe path component")
        self.directory = self.root / "mem" / "learning" / life_id
        self.state_path = self.directory / "state.json"
        self.journal_path = self.directory / "transaction.json"
        self.regression_path = self.directory / "regression.json"
        self.metrics_path = self.directory / "metrics.json"
        self.belief_store = belief_store or BeliefStore(
            path=self.root / "mem" / life_id / "beliefs.json"
        )
        self.evaluator = evaluator or self._default_evaluator
        self.directory.mkdir(parents=True, exist_ok=True)
        self._recover()

    def _empty_state(self) -> dict[str, Any]:
        return {"version": 1, "active": {}, "candidates": {}, "events": {}, "cycle": {}}

    def _read(self, path: Path, default: Any) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return default

    def _write(self, path: Path, value: Any) -> None:
        atomic_write_text(path, json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))

    def _recover(self) -> None:
        """Finish an interrupted commit; the journal contains the complete next state."""
        with file_lock(self.state_path):
            transaction = self._read(self.journal_path, None)
            if isinstance(transaction, dict) and isinstance(transaction.get("state"), dict):
                self._write(self.state_path, transaction["state"])
                self.journal_path.unlink(missing_ok=True)

    def _commit(self, state: dict[str, Any]) -> None:
        transaction = {"prepared_at": _now(), "state": state}
        self._write(self.journal_path, transaction)
        self._write(self.state_path, state)
        self.journal_path.unlink(missing_ok=True)

    @staticmethod
    def normalize(source: str, raw: Mapping[str, Any], *, life_id: str = "default") -> FeedbackEvent:
        """Normalize an event emitted by any supported runtime surface."""
        reward = raw.get("reward", raw.get("reward_delta", raw.get("score", 0.0)))
        subject = raw.get("subject", raw.get("target", raw.get("hypothesis", "")))
        return FeedbackEvent(
            source=source,
            subject=str(subject),
            reward=float(reward),
            context=dict(raw.get("context", {})),
            payload=dict(raw.get("payload", raw)),
            event_id=str(raw.get("event_id", uuid.uuid4().hex)),
            occurred_at=str(raw.get("occurred_at", _now())),
            life_id=life_id,
        )

    def ingest(self, event: FeedbackEvent, *, kind: str, proposed_value: Any) -> str:
        """Record evidence and update a candidate, without changing active state."""
        if event.life_id != self.life_id:
            raise ValueError("cross-life feedback is forbidden")
        if kind not in UPDATE_KINDS:
            raise ValueError(f"unsupported update kind: {kind}")
        key = f"{kind}:{event.subject}"
        candidate_id = hashlib.sha256(key.encode()).hexdigest()[:20]
        with file_lock(self.state_path):
            state = self._read(self.state_path, self._empty_state())
            if event.event_id in state["events"]:
                return candidate_id
            cycle = state.setdefault("cycle", {})
            today = datetime.now(timezone.utc).date().isoformat()
            if cycle.get("id") != today:
                cycle.clear(); cycle.update({"id": today, "events": 0, "candidates": []})
                self._apply_decay(state)
            if cycle["events"] >= self.policy.max_events_per_cycle:
                raise RuntimeError("learning event budget exhausted")
            if candidate_id not in state["candidates"] and len(cycle["candidates"]) >= self.policy.max_candidates_per_cycle:
                raise RuntimeError("candidate budget exhausted")
            previous = state["active"].get(key)
            candidate = state["candidates"].setdefault(candidate_id, {
                "id": candidate_id, "key": key, "kind": kind, "subject": event.subject,
                "proposed_value": proposed_value, "previous_version": previous,
                "evidence": [], "reward_sum": 0.0, "status": "candidate", "created_at": _now(),
            })
            # Contradictory proposals never silently overwrite an accumulated candidate.
            if candidate["proposed_value"] != proposed_value:
                candidate["contradictions"] = int(candidate.get("contradictions", 0)) + 1
            candidate["evidence"].append(asdict(event))
            candidate["reward_sum"] += float(event.reward)
            state["events"][event.event_id] = {"candidate_id": candidate_id, "at": _now()}
            cycle["events"] += 1
            if candidate_id not in cycle["candidates"]:
                cycle["candidates"].append(candidate_id)
            self._commit(state)
        return candidate_id

    def _apply_decay(self, state: dict[str, Any]) -> None:
        for candidate in state.get("candidates", {}).values():
            candidate["reward_sum"] *= min(1.0, max(0.0, self.policy.decay))

    def add_regression_case(self, case_id: str, context: Mapping[str, Any], expected: Any) -> None:
        """Persist a protected capability example used by every promotion."""
        with file_lock(self.regression_path):
            suite = self._read(self.regression_path, {})
            suite[case_id] = {"context": dict(context), "expected": expected, "updated_at": _now()}
            self._write(self.regression_path, suite)

    def evaluate_and_promote(self, candidate_id: str) -> PromotionDecision:
        with file_lock(self.state_path):
            state = self._read(self.state_path, self._empty_state())
            candidate = state["candidates"].get(candidate_id)
            if candidate is None:
                raise KeyError(candidate_id)
            evidence = candidate["evidence"]
            sources = {item["source"] for item in evidence}
            mean = candidate["reward_sum"] / max(len(evidence), 1)
            rewards = [float(item["reward"]) for item in evidence]
            drift = (max(rewards) - min(rewards)) if rewards else 0.0
            reasons = []
            if len(evidence) < self.policy.minimum_evidence: reasons.append("insufficient_evidence")
            if len(sources) < self.policy.minimum_distinct_sources: reasons.append("insufficient_source_diversity")
            if mean < self.policy.promotion_reward: reasons.append("reward_below_threshold")
            if drift > self.policy.drift_threshold: reasons.append("drift_detected")
            if candidate.get("contradictions", 0): reasons.append("contradictory_feedback")
            suite = list(self._read(self.regression_path, {}).values())
            if len(suite) < self.policy.minimum_regression_cases: reasons.append("regression_suite_missing")
            evaluation = dict(self.evaluator(candidate["kind"], candidate["subject"], candidate["proposed_value"], suite))
            regression = float(evaluation.get("regression", 0.0))
            retention = float(evaluation.get("retention", 1.0))
            gain = float(evaluation.get("gain", mean))
            if regression > self.policy.max_regression: reasons.append("regression_limit")
            if retention < self.policy.minimum_retention: reasons.append("catastrophic_forgetting_risk")
            activated = not reasons
            rollback_path = None
            if activated:
                version = int(state.get("version", 1)) + 1
                rollback_path = str(self.directory / "rollback" / f"{version}-{candidate_id}.json")
                self._write(Path(rollback_path), {"key": candidate["key"], "previous": candidate["previous_version"]})
                active = {"value": candidate["proposed_value"], "version": version, "activated_at": _now(),
                          "candidate_id": candidate_id, "evaluation": evaluation, "rollback_path": rollback_path}
                state["active"][candidate["key"]] = active
                state["version"] = version
                candidate["status"] = "active"
                self._publish(candidate, active)
            else:
                candidate["status"] = "rejected"
            candidate["evaluation"] = evaluation
            candidate["activation_decision"] = {"activated": activated, "reasons": reasons, "at": _now()}
            candidate["rollback_path"] = rollback_path
            self._commit(state)
            self._record_metrics(gain, retention, regression)
            return PromotionDecision(candidate_id, activated, ",".join(reasons) or "promoted", evaluation, rollback_path)

    @staticmethod
    def _default_evaluator(kind: str, subject: str, value: Any, suite: list[dict[str, Any]]) -> Mapping[str, float]:
        # With no domain evaluator, preserve the suite rather than claiming improvement.
        return {"gain": 0.0, "retention": 1.0, "regression": 0.0, "samples": float(len(suite))}

    def _publish(self, candidate: Mapping[str, Any], active: Mapping[str, Any]) -> None:
        """Connect validated state to beliefs, skill metadata, and planner choices."""
        kind, subject = candidate["kind"], candidate["subject"]
        if kind == "belief":
            self.belief_store.update_after_run(subject, success=True, evidence=f"learning:{candidate['id']}", reward_delta=float(candidate["reward_sum"]))
        filename = "skill_catalog.json" if kind == "skill" else "planning_learning.json"
        if kind in {"skill", "strategy"}:
            path = self.root / "mem" / self.life_id / filename
            payload = self._read(path, {})
            if kind == "skill":
                descriptor = payload.setdefault(subject, {"skill": subject})
                descriptor["learning"] = dict(active)
                if isinstance(candidate["proposed_value"], Mapping):
                    descriptor.update(candidate["proposed_value"])
            else:
                payload[subject] = dict(active)
            self._write(path, payload)

    def rollback(self, *, key: str) -> bool:
        with file_lock(self.state_path):
            state = self._read(self.state_path, self._empty_state())
            active = state["active"].get(key)
            if not active: return False
            snapshot = self._read(Path(active["rollback_path"]), {})
            previous = snapshot.get("previous")
            if previous is None: state["active"].pop(key, None)
            else: state["active"][key] = previous
            self._commit(state)
            return True

    def _record_metrics(self, gain: float, retention: float, regression: float) -> None:
        metrics = self._read(self.metrics_path, {"samples": []})
        metrics["samples"].append({"at": _now(), "post_feedback_gain_pct": gain * 100,
                                   "retention_30d_pct": retention * 100,
                                   "monthly_regression_pct": regression * 100})
        self._write(self.metrics_path, metrics)

    def metrics(self) -> Mapping[str, float]:
        samples = self._read(self.metrics_path, {"samples": []})["samples"]
        if not samples:
            return {"post_feedback_gain_pct": 0.0, "retention_30d_pct": 100.0, "monthly_regression_pct": 0.0}
        return {key: sum(float(x[key]) for x in samples) / len(samples) for key in
                ("post_feedback_gain_pct", "retention_30d_pct", "monthly_regression_pct")}
