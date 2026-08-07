"""Safe imitation learning and durable experiment history."""

from __future__ import annotations

import ast
import hashlib
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from singular.io_utils import append_jsonl_line, atomic_write_text
from singular.life.sandbox import SandboxError, run as sandbox_run
from singular.life.skill_catalog import refresh_skill_catalog


@dataclass(frozen=True)
class Demonstration:
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


class ImitationEngine:
    """Learns a deterministic observation/action policy behind safety gates."""

    def __init__(self, root: Path, *, min_improvement: float = 0.01) -> None:
        self.root = Path(root)
        self.store = self.root / "mem" / "learning"
        self.skills_dir = self.root / "skills"
        self.min_improvement = float(min_improvement)
        self.pending: list[Demonstration] = []
        self.store.mkdir(parents=True, exist_ok=True)
        self._load_pending()

    @staticmethod
    def extract_sequences(
        payload: Demonstration | Mapping[str, Any],
    ) -> list[tuple[Any, Any]]:
        """Normalize either parallel arrays or structured ``steps``."""

        if isinstance(payload, Demonstration):
            observations, actions = payload.observations, payload.actions
        elif "steps" in payload:
            steps = payload.get("steps", [])
            return [
                (step["observation"], step["action"])
                for step in steps
                if isinstance(step, Mapping)
                and "observation" in step
                and "action" in step
            ]
        else:
            observations = payload.get("observations", [])
            actions = payload.get("actions", [])
        if len(observations) != len(actions):
            raise ValueError("observations and actions must have the same length")
        return list(zip(observations, actions))

    def ingest(self, payload: Demonstration | Mapping[str, Any]) -> Demonstration:
        pairs = self.extract_sequences(payload)
        name = (
            payload.name
            if isinstance(payload, Demonstration)
            else str(payload.get("name", "imitated_skill"))
        )
        metadata = (
            payload.metadata
            if isinstance(payload, Demonstration)
            else payload.get("metadata")
        )
        demonstration = Demonstration(
            [p[0] for p in pairs], [p[1] for p in pairs], name, metadata
        )
        if not pairs:
            raise ValueError(
                "a demonstration must contain at least one observation-action pair"
            )
        self.pending.append(demonstration)
        self._event(
            "demonstrations", {"type": "demonstration", **asdict(demonstration)}
        )
        self._save_pending()
        return demonstration

    ingest_demonstration = ingest

    def propose_candidate(self, demonstration: Demonstration) -> str:
        pairs = self.extract_sequences(demonstration)
        default = max(
            set(map(repr, demonstration.actions)),
            key=list(map(repr, demonstration.actions)).count,
        )
        source = (
            '"""Capability_tags: imitation, learned\nReliability: 0.5\nEstimated_cost: 0.1\n"""\n'
            f"_POLICY = {pairs!r}\n_DEFAULT = {default}\n\n"
            "def run(observation):\n"
            "    for seen, action in _POLICY:\n"
            "        if seen == observation:\n"
            "            return action\n"
            "    return _DEFAULT\n"
        )
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
            outcome = self.evaluate_and_publish(demo, self.propose_candidate(demo))
        finally:
            self._save_pending()
        return outcome

    def evaluate_and_publish(self, demo: Demonstration, source: str) -> LearningOutcome:
        name = self._safe_name(demo.name)
        pairs = self.extract_sequences(demo)
        baseline = self._baseline_accuracy([a for _, a in pairs])
        reason = self._static_safety_reason(source)
        score = 0.0
        if reason is None:
            correct = 0
            try:
                for observation, action in pairs:
                    observed = sandbox_run(f"{source}\nresult = run({observation!r})")
                    correct += observed == action
                score = correct / len(pairs)
            except (Exception, SandboxError) as exc:
                reason = f"sandbox rejected candidate: {exc}"
        accepted = reason is None and score >= baseline + self.min_improvement
        result = {
            "type": "evaluation",
            "skill": name,
            "score": score,
            "baseline": baseline,
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
            quarantine = (
                self.store / "quarantine" / f"{name}-{int(time.time() * 1000)}.py"
            )
            quarantine.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_text(quarantine, source)
            return LearningOutcome(
                "quarantined", name, score, baseline, result["reason"]
            )

        target = self.skills_dir / f"{name}.py"
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        if target.exists():
            rollback = self.store / "rollback" / f"{name}-{int(time.time() * 1000)}.py"
            rollback.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_text(rollback, target.read_text(encoding="utf-8"))
        atomic_write_text(target, source)
        try:
            refresh_skill_catalog(skills_dir=self.skills_dir, mem_dir=self.root / "mem")
        except Exception:
            target.unlink(missing_ok=True)
            raise
        return LearningOutcome("active", name, score, baseline, "validated", target)

    def _static_safety_reason(self, source: str) -> str | None:
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            return f"invalid syntax: {exc.msg}"
        forbidden = (
            ast.Import,
            ast.ImportFrom,
            ast.With,
            ast.AsyncWith,
            ast.Global,
            ast.Nonlocal,
        )
        dangerous = {
            "open",
            "exec",
            "eval",
            "compile",
            "__import__",
            "os",
            "sys",
            "subprocess",
            "socket",
        }
        for node in ast.walk(tree):
            if isinstance(node, forbidden):
                return "governance rejected forbidden syntax"
            if isinstance(node, ast.Name) and node.id in dangerous:
                return f"governance rejected dangerous name: {node.id}"
        return None

    @staticmethod
    def _baseline_accuracy(actions: Sequence[Any]) -> float:
        representations = [repr(action) for action in actions]
        return max(representations.count(item) for item in set(representations)) / len(
            actions
        )

    @staticmethod
    def _safe_name(name: str) -> str:
        safe = "".join(c if c.isalnum() or c == "_" else "_" for c in name).strip("_")
        return safe or "imitated_skill"

    def _event(self, stream: str, payload: dict[str, Any]) -> None:
        append_jsonl_line(self.store / f"{stream}.jsonl", payload)

    def _result_count(self, skill: str) -> int:
        path = self.store / "results.jsonl"
        if not path.exists():
            return 1
        return sum(
            1
            for line in path.read_text(encoding="utf-8").splitlines()
            if f'"skill": "{skill}"' in line
        )

    def _save_pending(self) -> None:
        atomic_write_text(
            self.store / "state.json",
            json.dumps(
                {"pending": [asdict(item) for item in self.pending]},
                ensure_ascii=False,
                indent=2,
            ),
        )

    def _load_pending(self) -> None:
        path = self.store / "state.json"
        if not path.exists():
            return
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.pending = [
                Demonstration(**item) for item in payload.get("pending", [])
            ]
        except (ValueError, TypeError, json.JSONDecodeError):
            self.pending = []
