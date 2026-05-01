from __future__ import annotations
import json
from dataclasses import dataclass, field
from pathlib import Path

@dataclass
class DeferredPenalty:
    due_tick: int
    energy_delta: float = 0.0
    health_delta: float = 0.0
    mortality_delta: float = 0.0

@dataclass
class PersistentWorldState:
    rarity: float = 0.5
    reputation: float = 0.5
    risks: float = 0.5
    opportunities: float = 0.5
    mortality_pressure: float = 0.0
    deferred_penalties: list[DeferredPenalty] = field(default_factory=list)
    @classmethod
    def load(cls, path: Path) -> 'PersistentWorldState':
        if not path.exists():
            return cls()
        payload = json.loads(path.read_text(encoding='utf-8'))
        return cls(
            rarity=float(payload.get('rarity', 0.5)),
            reputation=float(payload.get('reputation', 0.5)),
            risks=float(payload.get('risks', 0.5)),
            opportunities=float(payload.get('opportunities', 0.5)),
            mortality_pressure=float(payload.get('mortality_pressure', 0.0)),
            deferred_penalties=[DeferredPenalty(**item) for item in payload.get('deferred_penalties', [])],
        )
    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding='utf-8')
    def to_dict(self) -> dict[str, object]:
        return {'rarity': self.rarity, 'reputation': self.reputation, 'risks': self.risks, 'opportunities': self.opportunities, 'mortality_pressure': self.mortality_pressure, 'deferred_penalties': [p.__dict__ for p in self.deferred_penalties]}
    def apply_world_delta(self, world_delta: dict[str, float]) -> None:
        self.rarity = max(0.0, min(1.0, self.rarity + world_delta.get('rarity', 0.0)))
        self.reputation = max(0.0, min(1.0, self.reputation + world_delta.get('reputation', 0.0)))
        self.risks = max(0.0, min(1.0, self.risks + world_delta.get('risks', 0.0)))
        self.opportunities = max(0.0, min(1.0, self.opportunities + world_delta.get('opportunities', 0.0)))
    def schedule_penalties(self, current_tick: int, delayed_penalties: list[dict[str, float | int]]) -> None:
        for penalty in delayed_penalties:
            self.deferred_penalties.append(DeferredPenalty(due_tick=current_tick + max(1, int(penalty.get('ticks', 0))), energy_delta=float(penalty.get('energy_delta', 0.0)), health_delta=float(penalty.get('health_delta', 0.0)), mortality_delta=float(penalty.get('mortality_delta', 0.0))))
    def consume_due_penalties(self, current_tick: int) -> list[DeferredPenalty]:
        due = [p for p in self.deferred_penalties if p.due_tick <= current_tick]
        self.deferred_penalties = [p for p in self.deferred_penalties if p.due_tick > current_tick]
        return due
