from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Type


class DSLValidationError(ValueError):
    """Raised when a patch fails DSL validation."""


def load_operator_rules(path: Path | None = None) -> Dict[str, Any]:
    """Load operator rules from the configuration without external deps.

    The ``operators.yaml`` file in this project is a very small subset of YAML
    that maps operator names to metadata. To avoid relying on the external
    ``pyyaml`` package, we parse the file manually and only keep the operator
    names and any simple ``key: value`` metadata indented beneath them.
    """

    if path is None:
        path = Path(__file__).resolve().parents[1] / "configs" / "operators.yaml"

    rules: Dict[str, Dict[str, Any]] = {}
    current: str | None = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        if not raw.startswith(" "):
            current = raw.rstrip(":").strip()
            rules[current] = {}
        elif current:
            line = raw.strip()
            if ":" in line:
                key, value = line.split(":", 1)
                rules[current][key.strip()] = value.strip()
    return rules


OPERATOR_RULES = load_operator_rules()
OPERATOR_NAMES = set(OPERATOR_RULES.keys())

THETA_DIFF_LIMIT = 10
CYCLOMATIC_LIMIT = 10


@dataclass
class Operation:
    """Base class for all operations."""

    name: str

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Operation":
        name = data.get("op")
        if name not in OPERATOR_NAMES:
            raise DSLValidationError(f"Unknown operator: {name}")
        op_cls = OP_CLASSES.get(name, Operation)
        kwargs = {k: v for k, v in data.items() if k != "op"}
        return op_cls(name=name, **kwargs)


@dataclass
class ConstTune(Operation):
    delta: float = 0.0
    bounds: List[float] = field(default_factory=list)


@dataclass
class EqRewrite(Operation):
    rule_id: str = ""


@dataclass
class Inline(Operation):
    pass


@dataclass
class Extract(Operation):
    pass


@dataclass
class DeadcodeElim(Operation):
    pass


@dataclass
class MicroMemo(Operation):
    pass


OP_CLASSES: Dict[str, Type[Operation]] = {
    "CONST_TUNE": ConstTune,
    "EQ_REWRITE": EqRewrite,
    "INLINE": Inline,
    "EXTRACT": Extract,
    "DEADCODE_ELIM": DeadcodeElim,
    "MICRO_MEMO": MicroMemo,
}


@dataclass
class Patch:
    target: Dict[str, Any]
    ops: List[Operation]
    theta_diff: float
    purity: bool
    cyclomatic: int

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Patch":
        ops = [Operation.from_dict(d) for d in data.get("ops", [])]
        return cls(
            target=data.get("target", {}),
            ops=ops,
            theta_diff=data.get("theta_diff", 0.0),
            purity=data.get("purity", True),
            cyclomatic=data.get("cyclomatic", 0),
        )

    def validate(self) -> bool:
        if self.theta_diff > THETA_DIFF_LIMIT:
            raise DSLValidationError("θ_diff exceeds limit")
        if not self.purity:
            raise DSLValidationError("Patch must be pure")
        if self.cyclomatic > CYCLOMATIC_LIMIT:
            raise DSLValidationError("Cyclomatic complexity exceeds limit")
        return True
