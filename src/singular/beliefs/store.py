"""Persistent belief store with Bayesian updates and temporal forgetting."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import tempfile
from typing import Any, Iterable


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_datetime(value: str | None) -> datetime:
    if not value:
        return _utcnow()
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return _utcnow()
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


@dataclass
class BeliefRecord:
    """Belief entry attached to a hypothesis."""

    hypothesis: str
    confidence: float
    evidence: str
    updated_at: str
    alpha: float = 1.0
    beta: float = 1.0
    score_ema: float = 0.0
    runs: int = 0


class BeliefStore:
    """Store beliefs and update them after each mutation run."""

    def __init__(
        self,
        path: Path | None = None,
        *,
        prior_alpha: float = 1.0,
        prior_beta: float = 1.0,
        decay_per_day: float = 0.03,
        ttl_days: float = 45.0,
    ) -> None:
        base = Path(os.environ.get("SINGULAR_HOME", "."))
        self.path = path or (base / "mem" / "beliefs.json")
        self.prior_alpha = float(prior_alpha)
        self.prior_beta = float(prior_beta)
        self.decay_per_day = max(0.0, float(decay_per_day))
        self.ttl_days = max(0.0, float(ttl_days))
        self._beliefs = self._load()

    def _load(self) -> dict[str, BeliefRecord]:
        if not self.path.exists():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        if not isinstance(payload, dict):
            return {}
        beliefs: dict[str, BeliefRecord] = {}
        for key, value in payload.items():
            if not isinstance(key, str) or not isinstance(value, dict):
                continue
            beliefs[key] = BeliefRecord(
                hypothesis=key,
                confidence=float(value.get("confidence", 0.5)),
                evidence=str(value.get("evidence", "")),
                updated_at=str(value.get("updated_at", _utcnow().isoformat())),
                alpha=float(value.get("alpha", self.prior_alpha)),
                beta=float(value.get("beta", self.prior_beta)),
                score_ema=float(value.get("score_ema", 0.0)),
                runs=int(value.get("runs", 0)),
            )
        return beliefs

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {key: asdict(value) for key, value in self._beliefs.items()}
        tmp = tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=self.path.parent, delete=False
        )
        try:
            with tmp:
                tmp.write(json.dumps(payload, ensure_ascii=False, indent=2))
                tmp.flush()
                os.fsync(tmp.fileno())
            os.replace(tmp.name, self.path)
        finally:
            try:
                os.unlink(tmp.name)
            except FileNotFoundError:
                pass

    def list_beliefs(self) -> list[BeliefRecord]:
        return sorted(self._beliefs.values(), key=lambda item: item.confidence, reverse=True)

    def get_confidence(self, hypothesis: str, default: float = 0.5) -> float:
        if hypothesis in self._beliefs:
            return self._beliefs[hypothesis].confidence
        return default

    def _apply_decay(self, record: BeliefRecord, now: datetime) -> None:
        updated_at = _parse_datetime(record.updated_at)
        delta_days = max(0.0, (now - updated_at).total_seconds() / 86400.0)
        if delta_days <= 0.0 or self.decay_per_day <= 0.0:
            return
        retention = math.exp(-self.decay_per_day * delta_days)
        record.alpha = self.prior_alpha + (record.alpha - self.prior_alpha) * retention
        record.beta = self.prior_beta + (record.beta - self.prior_beta) * retention

    def _is_stale(self, record: BeliefRecord, now: datetime) -> bool:
        if self.ttl_days <= 0.0:
            return False
        age_days = max(0.0, (now - _parse_datetime(record.updated_at)).total_seconds() / 86400.0)
        near_prior = abs(record.alpha - self.prior_alpha) < 0.02 and abs(record.beta - self.prior_beta) < 0.02
        return age_days >= self.ttl_days and near_prior

    def forget_stale(self, *, when: datetime | None = None) -> int:
        now = when or _utcnow()
        removed = 0
        for key in list(self._beliefs):
            record = self._beliefs[key]
            self._apply_decay(record, now)
            if self._is_stale(record, now):
                self._beliefs.pop(key, None)
                removed += 1
            else:
                record.confidence = record.alpha / max(record.alpha + record.beta, 1e-9)
                record.updated_at = now.isoformat()
        if removed:
            self._save()
        return removed

    def update_after_run(
        self,
        hypothesis: str,
        *,
        success: bool,
        evidence: str,
        reward_delta: float = 0.0,
        when: datetime | None = None,
    ) -> BeliefRecord:
        now = when or _utcnow()
        record = self._beliefs.get(hypothesis) or BeliefRecord(
            hypothesis=hypothesis,
            confidence=0.5,
            evidence="",
            updated_at=now.isoformat(),
            alpha=self.prior_alpha,
            beta=self.prior_beta,
            score_ema=0.0,
            runs=0,
        )
        self._apply_decay(record, now)
        if success:
            record.alpha += 1.0
        else:
            record.beta += 1.0
        record.runs += 1
        record.score_ema = (record.score_ema * 0.8) + (float(reward_delta) * 0.2)
        record.confidence = record.alpha / max(record.alpha + record.beta, 1e-9)
        record.updated_at = now.isoformat()
        record.evidence = evidence
        self._beliefs[hypothesis] = record
        self._save()
        return record

    def reset(self, *, hypothesis: str | None = None, prefix: str | None = None) -> int:
        if hypothesis:
            deleted = int(self._beliefs.pop(hypothesis, None) is not None)
            self._save()
            return deleted
        if prefix:
            keys = [key for key in self._beliefs if key.startswith(prefix)]
            for key in keys:
                self._beliefs.pop(key, None)
            self._save()
            return len(keys)
        count = len(self._beliefs)
        self._beliefs = {}
        self._save()
        return count

    def operator_preference_bias(self, operator_names: Iterable[str]) -> dict[str, float]:
        biases: dict[str, float] = {}
        for name in operator_names:
            hypothesis = f"operator:{name}"
            record = self._beliefs.get(hypothesis)
            if record is None:
                biases[name] = 0.0
                continue
            confidence_shift = record.confidence - 0.5
            biases[name] = (confidence_shift * 0.4) + max(-0.2, min(0.2, record.score_ema))
        return biases

    def update_probabilistic_rule(
        self,
        *,
        context_key: str,
        strategy: str,
        success: bool,
        evidence: str,
        reward_delta: float = 0.0,
        when: datetime | None = None,
    ) -> BeliefRecord:
        rule_hypothesis = f"strategy:{context_key}->{strategy}"
        return self.update_after_run(
            rule_hypothesis,
            success=success,
            evidence=evidence,
            reward_delta=reward_delta,
            when=when,
        )

    def recommend_strategies(
        self,
        *,
        context_key: str,
        candidates: Iterable[str],
    ) -> list[tuple[str, float]]:
        now = _utcnow()
        ranked: list[tuple[str, float]] = []
        for name in candidates:
            hypothesis = f"strategy:{context_key}->{name}"
            record = self._beliefs.get(hypothesis)
            if record is None:
                continue
            self._apply_decay(record, now)
            record.confidence = record.alpha / max(record.alpha + record.beta, 1e-9)
            record.updated_at = now.isoformat()
            if self._is_stale(record, now):
                self._beliefs.pop(hypothesis, None)
                continue
            ranked.append((name, record.confidence))
        if ranked:
            self._save()
        ranked.sort(key=lambda item: item[1], reverse=True)
        return ranked
