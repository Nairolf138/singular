"""Evidence-bound observation and calibration of the agent's own decisions."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from singular.identity.self_model import SelfModelStore


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


class SelfObservationService:
    """Compare predicted and actual outcomes without turning guesses into facts.

    Every accepted observation has at least one durable evidence reference.  A
    domain score remains explicitly uncertain until three independent samples
    exist, and confidence is shrunk toward 0.5 while evidence is sparse.
    """

    MIN_EVIDENCE = 3
    REPEATED_FAILURES = 3

    def __init__(self, store: SelfModelStore | Path | str) -> None:
        self.store = (
            store if isinstance(store, SelfModelStore) else SelfModelStore(store)
        )

    def observe(self, observations: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
        model = self.store.read()
        meta = model["metacognition"]
        now = _now()
        processed = set(str(ref) for ref in meta.get("processed_evidence_refs", ()))
        for raw in observations:
            refs = [str(ref) for ref in raw.get("evidence_refs", ()) if str(ref)]
            if not refs or all(ref in processed for ref in refs):
                continue
            domain = str(raw.get("domain") or "general")
            prediction = _clamp(
                float(raw.get("prediction", raw.get("confidence", 0.5)))
            )
            success = bool(raw.get("success", False))
            outcome = 1.0 if success else 0.0
            error = abs(prediction - outcome)
            record = meta["domains"].setdefault(
                domain,
                {
                    "sample_count": 0,
                    "success_count": 0,
                    "mean_confidence": 0.0,
                    "brier_score": None,
                    "calibration_score": None,
                    "competence": None,
                    "limitations": [],
                    "uncertainty": 1.0,
                    "evidence_refs": [],
                },
            )
            n = int(record["sample_count"])
            record["sample_count"] = n + 1
            record["success_count"] = int(record["success_count"]) + int(success)
            record["mean_confidence"] = (
                (float(record["mean_confidence"]) * n) + prediction
            ) / (n + 1)
            previous_brier = float(record["brier_score"] or 0.0)
            brier = ((previous_brier * n) + (error * error)) / (n + 1)
            record["brier_score"] = brier
            # Shrink estimates toward ignorance until there is adequate evidence.
            weight = min(1.0, (n + 1) / self.MIN_EVIDENCE)
            record["calibration_score"] = 0.5 + ((1.0 - brier - 0.5) * weight)
            observed_rate = int(record["success_count"]) / (n + 1)
            record["competence"] = 0.5 + ((observed_rate - 0.5) * weight)
            record["uncertainty"] = 1.0 / ((n + 1) ** 0.5)
            record["evidence_refs"] = list(
                dict.fromkeys([*record["evidence_refs"], *refs])
            )[-100:]

            failure = str(
                raw.get("failure_condition") or raw.get("error_type") or ""
            ).strip()
            if not success and failure:
                item = meta["failure_conditions"].setdefault(
                    f"{domain}:{failure}",
                    {"count": 0, "domains": [domain], "evidence_refs": []},
                )
                item["count"] += 1
                item["evidence_refs"] = list(
                    dict.fromkeys([*item["evidence_refs"], *refs])
                )[-50:]
                if item["count"] >= self.REPEATED_FAILURES:
                    limitation = f"repeated_failure:{failure}"
                    if limitation not in record["limitations"]:
                        record["limitations"].append(limitation)
                    meta["recurring_errors"][f"{domain}:{failure}"] = dict(item)

            strategy = str(raw.get("strategy") or "").strip()
            if success and strategy:
                item = meta["effective_strategies"].setdefault(
                    strategy, {"success_count": 0, "evidence_refs": []}
                )
                item["success_count"] += 1
                item["evidence_refs"] = list(
                    dict.fromkeys([*item["evidence_refs"], *refs])
                )[-50:]
            bias = str(raw.get("observed_bias") or "").strip()
            if bias:
                item = meta["observed_biases"].setdefault(
                    bias, {"count": 0, "evidence_refs": []}
                )
                item["count"] += 1
                item["evidence_refs"] = list(
                    dict.fromkeys([*item["evidence_refs"], *refs])
                )[-50:]

            meta["calibration_history"].append(
                {
                    "observed_at": now,
                    "domain": domain,
                    "prediction": prediction,
                    "outcome": outcome,
                    "absolute_error": error,
                    "evidence_refs": refs,
                }
            )
            processed.update(refs)
        meta["calibration_history"] = meta["calibration_history"][-500:]
        meta["processed_evidence_refs"] = list(processed)[-1000:]
        meta["updated_at"] = now
        model["updated_at"] = now
        self.store.write(model)
        return model

    def observe_trace(
        self, trace: Mapping[str, Any], *, evidence_ref: str
    ) -> dict[str, Any]:
        decision = trace.get("decision", {})
        action = trace.get("action", {})
        result = trace.get("result", {})
        if not all(isinstance(part, Mapping) for part in (decision, action, result)):
            return self.store.read()
        return self.observe(
            [
                {
                    "domain": action.get("domain")
                    or action.get("action_type")
                    or action.get("kind")
                    or "general",
                    "prediction": decision.get(
                        "confidence", decision.get("predicted_success", 0.5)
                    ),
                    "success": result.get(
                        "success", float(result.get("gain_loss", 0.0)) > 0.0
                    ),
                    "error_type": result.get("error")
                    or result.get("failure_condition"),
                    "strategy": decision.get("operator") or action.get("strategy"),
                    "evidence_refs": [evidence_ref],
                }
            ]
        )

    def observe_episodes(self, episodes: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
        observations = []
        for index, episode in enumerate(episodes):
            if not isinstance(episode.get("decision"), Mapping) or not isinstance(
                episode.get("result"), Mapping
            ):
                continue
            ref = str(
                episode.get("trace_id") or episode.get("id") or f"episode:{index}"
            )
            trace = {
                "decision": episode["decision"],
                "action": episode.get("action", {}),
                "result": episode["result"],
            }
            decision, action, result = (
                trace["decision"],
                trace["action"],
                trace["result"],
            )
            observations.append(
                {
                    "domain": action.get("domain") or action.get("kind") or "general",
                    "prediction": decision.get("confidence", 0.5),
                    "success": result.get(
                        "success", float(result.get("gain_loss", 0)) > 0
                    ),
                    "error_type": result.get("error"),
                    "strategy": decision.get("operator"),
                    "evidence_refs": [ref],
                }
            )
        return self.observe(observations) if observations else self.store.read()

    def decision_context(self, domain: str) -> dict[str, Any]:
        record = self.store.read()["metacognition"]["domains"].get(domain, {})
        return dict(record) if isinstance(record, Mapping) else {}
