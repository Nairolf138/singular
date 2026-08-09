"""Evidence-based developmental stages and runtime capability gates.

Stages describe demonstrated maturity, never chronological age.  This module is
deliberately a *second* safety boundary: a stage may further restrict governance,
but can never grant an action rejected by governance or human approval policy.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from singular.io_utils import append_jsonl_line, atomic_write_text


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _unit(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


@dataclass(frozen=True)
class MaturityEvidence:
    calibration: float = 0.0
    stability: float = 0.0
    retention: float = 0.0
    skill_mastery: float = 0.0
    constraint_adherence: float = 0.0
    recovery: float = 0.0
    incidents: int = 0
    samples: int = 0

    def score(self, weights: Mapping[str, float] | None = None) -> float:
        weights = weights or {
            "calibration": 0.15,
            "stability": 0.2,
            "retention": 0.15,
            "skill_mastery": 0.2,
            "constraint_adherence": 0.2,
            "recovery": 0.1,
        }
        total = sum(max(0.0, float(v)) for v in weights.values()) or 1.0
        base = (
            sum(
                _unit(getattr(self, key, 0.0)) * max(0.0, float(weight))
                for key, weight in weights.items()
            )
            / total
        )
        return round(max(0.0, base - min(max(self.incidents, 0) * 0.2, 0.8)), 4)


@dataclass(frozen=True)
class DevelopmentalStage:
    id: str
    prerequisites: Mapping[str, float]
    allowed_skills: tuple[str, ...]
    autonomy: str
    max_difficulty: float
    supervision: str
    promotion: Mapping[str, Any]
    regression: Mapping[str, Any]
    exploration_budget: float
    allowed_actions: tuple[str, ...] = ()
    sensitive_actions: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "DevelopmentalStage":
        return cls(
            id=str(value["id"]),
            prerequisites=dict(value.get("prerequisites", {})),
            allowed_skills=tuple(value.get("allowed_skills", ())),
            autonomy=str(value.get("autonomy", "supervised")),
            max_difficulty=_unit(value.get("max_difficulty", 0)),
            supervision=str(value.get("supervision", "continuous")),
            promotion=dict(value.get("promotion", {})),
            regression=dict(value.get("regression", {})),
            exploration_budget=max(0.0, float(value.get("exploration_budget", 0))),
            allowed_actions=tuple(value.get("allowed_actions", ())),
            sensitive_actions=tuple(value.get("sensitive_actions", ())),
        )


@dataclass(frozen=True)
class GateDecision:
    allowed: bool
    reason: str
    stage: str
    requires_human_approval: bool = False


class DevelopmentalModel:
    """Persistent stage evaluator and common gate for all learning surfaces."""

    def __init__(
        self,
        root: Path | str,
        stages: Sequence[DevelopmentalStage],
        *,
        life_id: str = "default",
    ):
        if not stages:
            raise ValueError("at least one developmental stage is required")
        if not life_id or Path(life_id).name != life_id:
            raise ValueError("life_id must be a safe path component")
        self.root, self.stages, self.life_id = Path(root), tuple(stages), life_id
        self.directory = self.root / "mem" / "development" / life_id
        self.state_path = self.directory / "state.json"
        self.transitions_path = self.directory / "transitions.jsonl"
        self.directory.mkdir(parents=True, exist_ok=True)
        if not self.state_path.exists():
            self._write(
                {
                    "version": 1,
                    "stage_index": 0,
                    "qualifying_observations": 0,
                    "updated_at": _now(),
                    "last_evidence": None,
                }
            )

    @classmethod
    def from_config(
        cls, root: Path | str, config: Path | str, *, life_id: str = "default"
    ) -> "DevelopmentalModel":
        payload = json.loads(Path(config).read_text(encoding="utf-8"))
        return cls(
            root,
            [DevelopmentalStage.from_dict(item) for item in payload["stages"]],
            life_id=life_id,
        )

    def _read(self) -> dict[str, Any]:
        try:
            value = json.loads(self.state_path.read_text(encoding="utf-8"))
            index = int(value.get("stage_index", 0))
            value["stage_index"] = min(max(index, 0), len(self.stages) - 1)
            return value
        except (OSError, ValueError, json.JSONDecodeError):
            return {"version": 1, "stage_index": 0, "qualifying_observations": 0}

    def _write(self, state: Mapping[str, Any]) -> None:
        atomic_write_text(
            self.state_path,
            json.dumps(dict(state), ensure_ascii=False, indent=2, sort_keys=True),
        )

    @property
    def current(self) -> DevelopmentalStage:
        return self.stages[self._read()["stage_index"]]

    def observe(
        self, evidence: MaturityEvidence, *, justification: str
    ) -> DevelopmentalStage:
        if not justification.strip():
            raise ValueError("a transition assessment requires a justification")
        state, before = self._read(), self.current
        index, score = state["stage_index"], evidence.score()
        previous_index = index
        regression_limit = int(before.regression.get("incident_threshold", 1))
        regressed = evidence.incidents >= regression_limit and index > 0
        if regressed:
            index -= 1
            state["qualifying_observations"] = 0
            reason = "incident_threshold"
        else:
            next_stage = (
                self.stages[index + 1] if index + 1 < len(self.stages) else None
            )
            qualifies = next_stage is not None and evidence.samples >= int(
                next_stage.prerequisites.get("min_samples", 0)
            )
            qualifies = (
                qualifies
                and all(
                    _unit(getattr(evidence, key, 0)) >= float(value)
                    for key, value in next_stage.prerequisites.items()
                    if key != "min_samples"
                )
                and score >= float(next_stage.promotion.get("min_score", 0))
            )
            state["qualifying_observations"] = (
                int(state.get("qualifying_observations", 0)) + 1 if qualifies else 0
            )
            required = (
                int(next_stage.promotion.get("consecutive_observations", 1))
                if next_stage
                else 1
            )
            reason = "prerequisites_met" if qualifies else "stagnation"
            if qualifies and state["qualifying_observations"] >= required:
                index += 1
                state["qualifying_observations"] = 0
        state.update(
            {
                "stage_index": index,
                "updated_at": _now(),
                "last_evidence": asdict(evidence),
                "maturity_score": score,
            }
        )
        self._write(state)
        after = self.stages[index]
        append_jsonl_line(
            self.transitions_path,
            {
                "at": _now(),
                "from": before.id,
                "to": after.id,
                "kind": (
                    "regression"
                    if index < previous_index
                    else ("progression" if index > previous_index else "assessment")
                ),
                "reason": reason,
                "justification": justification,
                "score": score,
                "evidence": asdict(evidence),
            },
        )
        return after

    def gate(
        self,
        *,
        action: str,
        difficulty: float = 0.0,
        skill: str | None = None,
        governance_allowed: bool = True,
        human_approved: bool = False,
        sensitive: bool = False,
    ) -> GateDecision:
        stage = self.current
        if not governance_allowed:
            return GateDecision(False, "governance_denied", stage.id)
        if difficulty > stage.max_difficulty:
            return GateDecision(False, "difficulty_exceeds_stage", stage.id)
        if (
            skill
            and "*" not in stage.allowed_skills
            and skill not in stage.allowed_skills
        ):
            return GateDecision(False, "skill_not_available_at_stage", stage.id)
        if action not in stage.allowed_actions and "*" not in stage.allowed_actions:
            return GateDecision(False, "action_not_available_at_stage", stage.id)
        needs_approval = sensitive or action in stage.sensitive_actions
        if needs_approval and not human_approved:
            return GateDecision(False, "human_approval_required", stage.id, True)
        return GateDecision(True, "allowed", stage.id, needs_approval)

    def filter_quests(self, quests: Iterable[Any]) -> list[Any]:
        return [
            q
            for q in quests
            if float(getattr(q, "difficulty", 0.0)) <= self.current.max_difficulty
        ]

    def filter_skills(self, skills: Iterable[str]) -> list[str]:
        allowed = self.current.allowed_skills
        return (
            list(skills)
            if "*" in allowed
            else [skill for skill in skills if skill in allowed]
        )

    def exploration_budget(self, requested: float) -> float:
        return max(0.0, min(float(requested), self.current.exploration_budget))

    def dashboard_projection(self) -> dict[str, Any]:
        state, stage = self._read(), self.current
        return {
            "life_id": self.life_id,
            "stage": stage.id,
            "maturity_score": state.get("maturity_score", 0.0),
            "autonomy": stage.autonomy,
            "supervision": stage.supervision,
            "max_difficulty": stage.max_difficulty,
            "exploration_budget": stage.exploration_budget,
            "last_evidence": state.get("last_evidence"),
            "updated_at": state.get("updated_at"),
        }
