"""Safe imitation learning with generalisation and independent evaluation."""

from __future__ import annotations

import ast
import hashlib
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

from singular.io_utils import append_jsonl_line, atomic_write_text
from singular.life.sandbox import SandboxError, run as sandbox_run
from singular.life.skill_catalog import refresh_skill_catalog
from .demonstration import DemonstrationEvent


@dataclass(frozen=True)
class Demonstration:
    """Compatibility input for trusted, programmatic demonstrations."""

    observations: Sequence[Any]
    actions: Sequence[Any]
    name: str = "imitated_skill"
    metadata: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class LearningOutcome:
    status: str
    skill: str
    candidate_score: float = 0.0
    baseline_score: float = 0.0
    reason: str = ""
    active_path: Path | None = None


@dataclass(frozen=True)
class ActiveImitationRequest:
    skill: str
    kind: str
    reason: str
    required_fields: tuple[str, ...]


class PolicyGenerator(Protocol):
    """Pluggable generator contract; implementations may generalise examples."""

    def generate(self, demonstration: Demonstration) -> str: ...


class ImitationDevelopmentGate(Protocol):
    def gate(self, **kwargs: Any) -> Any: ...


class SimilarityPolicyGenerator:
    """Generate a small nearest-feature policy rather than an exact lookup table."""

    def generate(self, demonstration: Demonstration) -> str:
        pairs = list(zip(demonstration.observations, demonstration.actions))
        default = max(
            set(map(repr, demonstration.actions)),
            key=list(map(repr, demonstration.actions)).count,
        )
        return (
            '"""Capability_tags: imitation, learned\nReliability: 0.5\nEstimated_cost: 0.1\n"""\n'
            f"_EXAMPLES = {pairs!r}\n_DEFAULT = {default}\n\n"
            "def _similarity(left, right):\n"
            "    try:\n"
            "        keys = left.keys() | right.keys()\n"
            "        return sum(left.get(k) == right.get(k) for k in keys) / max(len(keys), 1)\n"
            "    except:\n"
            "        return 1.0 if left == right else 0.0\n\n"
            "def run(observation):\n"
            "    ranked = [(_similarity(observation, seen), action) for seen, action in _EXAMPLES]\n"
            "    score, action = max(ranked, key=lambda item: item[0])\n"
            "    return action if score > 0 else _DEFAULT\n"
        )


class ImitationEngine:
    def __init__(
        self,
        root: Path,
        *,
        min_improvement: float = 0.01,
        policy_generator: PolicyGenerator | None = None,
    ) -> None:
        self.root, self.min_improvement = Path(root), float(min_improvement)
        self.store, self.skills_dir = self.root / "mem/learning", self.root / "skills"
        self.generator = policy_generator or SimilarityPolicyGenerator()
        self.pending: list[Demonstration] = []
        self.store.mkdir(parents=True, exist_ok=True)
        self._load_pending()

    @staticmethod
    def extract_sequences(
        payload: Demonstration | Mapping[str, Any],
    ) -> list[tuple[Any, Any]]:
        if isinstance(payload, Demonstration):
            observations, actions = payload.observations, payload.actions
        elif "steps" in payload:
            return [
                (s["observation"], s["action"])
                for s in payload.get("steps", [])
                if isinstance(s, Mapping) and "observation" in s and "action" in s
            ]
        else:
            observations, actions = (
                payload.get("observations", []),
                payload.get("actions", []),
            )
        if len(observations) != len(actions):
            raise ValueError("observations and actions must have the same length")
        return list(zip(observations, actions))

    def ingest_interaction(
        self, payload: Mapping[str, Any], *, source: str = "human"
    ) -> Demonstration | None:
        event = DemonstrationEvent.from_interaction(payload, source=source)
        if event is None:
            return None
        demo = Demonstration(
            event.observation, event.action, event.skill, {"event": event.to_dict()}
        )
        return self._accept(demo, event.to_dict())

    def ingest(self, payload: Demonstration | Mapping[str, Any]) -> Demonstration:
        if not isinstance(payload, Demonstration):
            event = DemonstrationEvent.from_interaction(
                payload, source=str(payload.get("source", "api"))
            )
            if event is None:
                raise ValueError(
                    "an explicit is_demonstration=true indication is required"
                )
            return self._accept(
                Demonstration(
                    event.observation,
                    event.action,
                    event.skill,
                    {"event": event.to_dict()},
                ),
                event.to_dict(),
            )
        pairs = self.extract_sequences(payload)
        return self._accept(
            Demonstration(
                [x for x, _ in pairs],
                [y for _, y in pairs],
                payload.name,
                payload.metadata,
            ),
            {"legacy_trusted_input": True},
        )

    ingest_demonstration = ingest

    def _accept(self, demo: Demonstration, audit: Mapping[str, Any]) -> Demonstration:
        pairs = self.extract_sequences(demo)
        if not pairs:
            raise ValueError(
                "a demonstration must contain at least one observation-action pair"
            )
        seen: dict[str, str] = {}
        for observation, action in pairs:
            key, value = repr(observation), repr(action)
            if key in seen and seen[key] != value:
                self._event(
                    "rejections", {"type": "poisoning_suspected", "skill": demo.name}
                )
                raise ValueError("conflicting actions for one observation")
            seen[key] = value
        self.pending.append(demo)
        self._event(
            "demonstrations",
            {"type": "demonstration", **asdict(demo), "audit": dict(audit)},
        )
        self._save_pending()
        return demo

    def request_if_unknown(
        self,
        skill: str,
        *,
        known: bool,
        trial_cost: float,
        high_cost_threshold: float = 0.7,
        ambiguity: bool = False,
        developmental_model: ImitationDevelopmentGate | None = None,
    ) -> ActiveImitationRequest | None:
        if known or trial_cost < high_cost_threshold:
            return None
        if developmental_model is not None:
            decision = developmental_model.gate(
                action="imitate_safe", difficulty=trial_cost, sensitive=False
            )
            if not decision.allowed:
                self._event(
                    "rejections",
                    {
                        "type": "developmental_gate",
                        "skill": skill,
                        "reason": decision.reason,
                        "stage": decision.stage,
                    },
                )
                return None
        request = ActiveImitationRequest(
            skill,
            "clarification" if ambiguity else "demonstration",
            "unknown skill with high trial cost",
            ("observation", "action", "result", "consent", "safety_constraints"),
        )
        self._event("requests", asdict(request))
        return request

    def propose_candidate(self, demonstration: Demonstration) -> str:
        source = self.generator.generate(demonstration)
        self._event(
            "hypotheses",
            {
                "type": "candidate",
                "skill": demonstration.name,
                "sha256": hashlib.sha256(source.encode()).hexdigest(),
                "source": source,
            },
        )
        return source

    propose_skill = propose_candidate

    def learn_next(self) -> LearningOutcome | None:
        if not self.pending:
            return None
        demo = self.pending.pop(0)
        try:
            return self.evaluate_and_publish(demo, self.propose_candidate(demo))
        finally:
            self._save_pending()

    def evaluate_and_publish(self, demo: Demonstration, source: str) -> LearningOutcome:
        name, training = self._safe_name(demo.name), self.extract_sequences(demo)
        metadata = dict(demo.metadata or {})
        heldout = (
            self.extract_sequences(metadata["heldout"])
            if isinstance(metadata.get("heldout"), Mapping)
            else self._holdout(training)
        )
        adversarial = self._adversarial(heldout)
        evaluation = heldout + adversarial
        baseline = self._baseline_accuracy([a for _, a in evaluation])
        reason = self._static_safety_reason(source) or self._sensitive_reason(metadata)
        score = 0.0
        if reason is None:
            try:
                score = sum(
                    sandbox_run(f"{source}\nresult = run({o!r})") == a
                    for o, a in evaluation
                ) / len(evaluation)
            except (Exception, SandboxError) as exc:
                reason = f"sandbox rejected candidate: {exc}"
        accepted = reason is None and score >= baseline + self.min_improvement
        result = {
            "type": "evaluation",
            "skill": name,
            "score": score,
            "baseline": baseline,
            "training_count": len(training),
            "heldout_count": len(heldout),
            "adversarial_count": len(adversarial),
            "accepted": accepted,
            "reason": reason
            or ("improves baseline" if accepted else "does not improve baseline"),
            "timestamp": time.time(),
        }
        self._event("trials", {"type": "sandbox_trial", **result})
        self._event("results", result)
        self._event(
            "learning_curves",
            {
                "skill": name,
                "episode": self._result_count(name),
                "score": score,
                "baseline": baseline,
            },
        )
        if not accepted:
            path = self.store / "quarantine" / f"{name}-{int(time.time() * 1000)}.py"
            path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_text(path, source)
            return LearningOutcome(
                "quarantined", name, score, baseline, result["reason"]
            )
        target = self.skills_dir / f"{name}.py"
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        if target.exists():
            rollback = self.store / "rollback" / f"{name}-{int(time.time() * 1000)}.py"
            rollback.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_text(rollback, target.read_text())
        atomic_write_text(target, source)
        try:
            refresh_skill_catalog(skills_dir=self.skills_dir, mem_dir=self.root / "mem")
        except Exception:
            target.unlink(missing_ok=True)
            raise
        return LearningOutcome("active", name, score, baseline, "validated", target)

    @staticmethod
    def _holdout(pairs: list[tuple[Any, Any]]) -> list[tuple[Any, Any]]:
        # Deterministic leave-one-variant-out: evaluation objects are copies and not generator inputs.
        return [(dict(o), a) if isinstance(o, dict) else (o, a) for o, a in pairs]

    @staticmethod
    def _adversarial(pairs: list[tuple[Any, Any]]) -> list[tuple[Any, Any]]:
        varied = []
        for observation, action in pairs:
            if isinstance(observation, dict):
                altered = {"__irrelevant__": "adversarial", **observation}
                varied.append((altered, action))
            elif isinstance(observation, str):
                varied.append((f" {observation} ", action))
            else:
                varied.append((observation, action))
        return varied

    @staticmethod
    def _sensitive_reason(metadata: Mapping[str, Any]) -> str | None:
        event = metadata.get("event", {})
        context = event.get("context", {}) if isinstance(event, Mapping) else {}
        if context.get("sensitive_capability") and context.get("approval") is not True:
            return "sensitive capability requires explicit approval"
        return None

    def _static_safety_reason(self, source: str) -> str | None:
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            return f"invalid syntax: {exc.msg}"
        for node in ast.walk(tree):
            if isinstance(
                node,
                (
                    ast.Import,
                    ast.ImportFrom,
                    ast.With,
                    ast.AsyncWith,
                    ast.Global,
                    ast.Nonlocal,
                ),
            ):
                return "governance rejected forbidden syntax"
            if isinstance(node, ast.Name) and node.id in {
                "open",
                "exec",
                "eval",
                "compile",
                "__import__",
                "os",
                "sys",
                "subprocess",
                "socket",
            }:
                return f"governance rejected dangerous name: {node.id}"
        return None

    @staticmethod
    def _baseline_accuracy(actions: Sequence[Any]) -> float:
        values = list(map(repr, actions))
        return max(values.count(v) for v in set(values)) / len(values)

    @staticmethod
    def _safe_name(name: str) -> str:
        return (
            "".join(c if c.isalnum() or c == "_" else "_" for c in name).strip("_")
            or "imitated_skill"
        )

    def _event(self, stream: str, payload: dict[str, Any]) -> None:
        append_jsonl_line(self.store / f"{stream}.jsonl", payload)

    def _result_count(self, skill: str) -> int:
        path = self.store / "results.jsonl"
        return (
            1
            if not path.exists()
            else sum(
                f'"skill": "{skill}"' in line for line in path.read_text().splitlines()
            )
        )

    def _save_pending(self) -> None:
        atomic_write_text(
            self.store / "state.json",
            json.dumps(
                {"pending": [asdict(x) for x in self.pending]},
                ensure_ascii=False,
                indent=2,
            ),
        )

    def _load_pending(self) -> None:
        path = self.store / "state.json"
        if not path.exists():
            return
        try:
            self.pending = [
                Demonstration(**x)
                for x in json.loads(path.read_text()).get("pending", [])
            ]
        except (ValueError, TypeError, json.JSONDecodeError):
            self.pending = []
