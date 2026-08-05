from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from singular.events import get_global_event_bus
from singular.governance.policy import MutationGovernancePolicy
from singular.memory import read_skills, write_skills

from .skill_catalog import refresh_skill_catalog
from .skill_validation import validate_generated_skill


@dataclass(frozen=True)
class SkillGenesisResult:
    accepted: bool
    skill_name: str
    target: Path
    reason: str
    policy_level: str
    rolled_back: bool = False


@dataclass(frozen=True)
class SkillSpec:
    """Minimal mandatory specification for coverage-gap skill genesis."""

    name: str
    signature: str
    examples: list[dict[str, object]]
    success_criteria: str
    cooldown: int
    expected_impact: str


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_skill_name(seed: str) -> str:
    normalized = "".join(ch.lower() if ch.isalnum() else "_" for ch in seed).strip("_")
    if not normalized:
        normalized = "autogen_skill"
    while "__" in normalized:
        normalized = normalized.replace("__", "_")
    return normalized


def _render_skill_template(skill_name: str, spec: SkillSpec | None = None) -> str:
    spec_block = ""
    if spec is not None:
        spec_block = "\nSPEC = " + repr(asdict(spec)) + "\n"
    return (
        '"""Auto-generated skill scaffold.\n'
        "Created by life.skill_genesis with governance safeguards.\n"
        '"""\n\n'
        f"{spec_block}\n"
        "def run(context: dict | None = None) -> dict:\n"
        '    """Run a deterministic safe placeholder skill."""\n'
        "    context = context or {}\n"
        "    return {\n"
        f'        "skill": "{skill_name}",\n'
        '        "status": "ready",\n'
        '        "received_key_count": len(context),\n'
        "    }\n"
    )


def _publish_unresolved(payload: dict[str, object]) -> None:
    """Publish and journal a coverage-gap unresolved event."""

    get_global_event_bus().publish("coverage_gap.unresolved", payload)


def _append_journal(mem_dir: Path, payload: dict[str, object]) -> None:
    journal = mem_dir / "skill_genesis.jsonl"
    journal.parent.mkdir(parents=True, exist_ok=True)
    with journal.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _coerce_examples(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    examples: list[dict[str, object]] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        input_value = item.get("input", item.get("inputs"))
        output_value = item.get("output", item.get("expected_output"))
        if input_value is None or output_value is None:
            continue
        examples.append({"input": input_value, "output": output_value})
    return examples


def _coverage_gap_spec_from_snapshot(
    skill_name: str,
    signal_snapshot: Mapping[str, object],
) -> tuple[SkillSpec | None, str]:
    raw_examples = signal_snapshot.get(
        "examples", signal_snapshot.get("coverage_gap_examples")
    )
    examples = _coerce_examples(raw_examples)
    success_criteria = signal_snapshot.get(
        "success_criteria", signal_snapshot.get("coverage_gap_success_criteria")
    )
    if not examples:
        return None, "coverage gap genesis requires at least one input/output example"
    if not isinstance(success_criteria, str) or not success_criteria.strip():
        return None, "coverage gap genesis requires a success criterion"
    signature = signal_snapshot.get(
        "signature", signal_snapshot.get("coverage_gap_signature")
    )
    if not isinstance(signature, str) or not signature.strip():
        signature = "run(context: dict | None = None) -> dict"
    cooldown = signal_snapshot.get(
        "cooldown", signal_snapshot.get("coverage_gap_cooldown", 1)
    )
    try:
        normalized_cooldown = max(1, int(cooldown))
    except (TypeError, ValueError):
        normalized_cooldown = 1
    impact = signal_snapshot.get(
        "expected_impact", signal_snapshot.get("coverage_gap_expected_impact")
    )
    if not isinstance(impact, str) or not impact.strip():
        impact = "reduce observed coverage_gap by satisfying the supplied examples"
    return (
        SkillSpec(
            name=skill_name,
            signature=signature,
            examples=examples,
            success_criteria=success_criteria.strip(),
            cooldown=normalized_cooldown,
            expected_impact=impact.strip(),
        ),
        "",
    )


def _spec_fingerprint(
    trigger: str, spec: SkillSpec | None, signal_snapshot: Mapping[str, object]
) -> str:
    if spec is None:
        payload: object = {"trigger": trigger, "signals": signal_snapshot}
    else:
        payload = {"trigger": trigger, "spec": asdict(spec) | {"name": "<normalized>"}}
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _journal_has_duplicate(mem_dir: Path, *, trigger: str, fingerprint: str) -> bool:
    journal = mem_dir / "skill_genesis.jsonl"
    if not journal.exists():
        return False
    for line in journal.read_text(encoding="utf-8").splitlines():
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (
            payload.get("trigger") == trigger
            and payload.get("spec_fingerprint") == fingerprint
        ):
            return True
    return False


def create_skill(
    *,
    skills_dir: Path,
    mem_dir: Path,
    governance_policy: MutationGovernancePolicy,
    trigger: str,
    signal_snapshot: dict[str, object],
) -> SkillGenesisResult:
    stem = _safe_skill_name(f"autogen_{trigger}")
    suffix = 0
    target = skills_dir / f"{stem}.py"
    while target.exists():
        suffix += 1
        target = skills_dir / f"{stem}_{suffix}.py"
    skill_name = target.stem
    spec: SkillSpec | None = None
    if trigger == "coverage_gap":
        spec, spec_error = _coverage_gap_spec_from_snapshot(skill_name, signal_snapshot)
        if spec_error:
            payload = {
                "ts": _utc_iso(),
                "event": "coverage_gap.unresolved",
                "skill": skill_name,
                "target": str(target),
                "trigger": trigger,
                "reason": spec_error,
                "signals": dict(signal_snapshot),
            }
            _append_journal(mem_dir, payload)
            _publish_unresolved(payload)
            return SkillGenesisResult(
                accepted=False,
                skill_name=skill_name,
                target=target,
                reason=spec_error,
                policy_level="unresolved",
            )
    fingerprint = _spec_fingerprint(trigger, spec, signal_snapshot)
    if _journal_has_duplicate(mem_dir, trigger=trigger, fingerprint=fingerprint):
        reason = "duplicate skill genesis request suppressed by diversity limit"
        payload = {
            "ts": _utc_iso(),
            "event": (
                "coverage_gap.unresolved"
                if trigger == "coverage_gap"
                else "skill_genesis_duplicate"
            ),
            "skill": skill_name,
            "target": str(target),
            "trigger": trigger,
            "reason": reason,
            "spec_fingerprint": fingerprint,
        }
        _append_journal(mem_dir, payload)
        if trigger == "coverage_gap":
            _publish_unresolved(payload)
        return SkillGenesisResult(False, skill_name, target, reason, "diversity_limit")

    proposal = governance_policy.simulate_write(
        target,
        root=skills_dir.parent,
        operation="skill_creation",
    )
    if not proposal.allowed:
        _append_journal(
            mem_dir,
            {
                "ts": _utc_iso(),
                "event": "skill_genesis_rejected",
                "skill": skill_name,
                "target": str(target),
                "policy_level": proposal.level,
                "reason": proposal.reason,
                "trigger": trigger,
                "spec_fingerprint": fingerprint,
            },
        )
        return SkillGenesisResult(
            accepted=False,
            skill_name=skill_name,
            target=target,
            reason=proposal.reason,
            policy_level=proposal.level,
        )

    source = (
        _render_skill_template(skill_name, spec)
        if spec is not None
        else _render_skill_template(skill_name)
    )
    skills_before = read_skills(mem_dir / "skills.json")
    staging_dir = skills_dir / ".staging"
    staged_path = staging_dir / target.name
    target_created = False
    try:
        staging_dir.mkdir(parents=True, exist_ok=True)
        staged_path.write_text(source, encoding="utf-8")
        validation = validate_generated_skill(source, expected_symbol="run")
        if not validation.ok:
            raise RuntimeError(validation.reason)
        os.replace(staged_path, target)
        decision = proposal
        target_created = True
        skills_after = dict(skills_before)
        skills_after[skill_name] = {
            "score": 0.0,
            "note": "auto-generated by skill genesis",
            "created_at": _utc_iso(),
            "trigger": trigger,
            "spec": asdict(spec) if spec is not None else None,
        }
        write_skills(skills_after, mem_dir / "skills.json")
        refresh_skill_catalog(skills_dir=skills_dir, mem_dir=mem_dir)
        _append_journal(
            mem_dir,
            {
                "ts": _utc_iso(),
                "event": "skill_genesis_created",
                "skill": skill_name,
                "target": str(target),
                "policy_level": decision.level,
                "reason": decision.reason,
                "trigger": trigger,
                "signals": signal_snapshot,
                "spec": asdict(spec) if spec is not None else None,
                "spec_fingerprint": fingerprint,
            },
        )
        return SkillGenesisResult(
            accepted=True,
            skill_name=skill_name,
            target=target,
            reason=decision.reason,
            policy_level=decision.level,
        )
    except Exception as exc:
        if target_created and target.exists():
            target.unlink()
        if staged_path.exists():
            staged_path.unlink()
        write_skills(skills_before, mem_dir / "skills.json")
        _append_journal(
            mem_dir,
            {
                "ts": _utc_iso(),
                "event": "autogen.validation_failed",
                "skill": skill_name,
                "target": str(target),
                "trigger": trigger,
                "error": str(exc),
            },
        )
        return SkillGenesisResult(
            accepted=False,
            skill_name=skill_name,
            target=target,
            reason=f"validation failed: {exc}",
            policy_level="validation_failed",
            rolled_back=True,
        )
