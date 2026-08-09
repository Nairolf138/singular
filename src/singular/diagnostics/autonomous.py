"""Shared, structured readiness diagnostics for autonomous operation."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, TypedDict

READY = 0
DEGRADED = 1
BLOCKED = 2
SCHEMA_VERSION = 1


class DiagnosticCheck(TypedDict):
    check_id: str
    severity: str
    state: str
    evidence: dict[str, Any]
    remediation_command: str | None


class AutonomousDiagnosticReport(TypedDict):
    schema_version: int
    status: str
    exit_code: int
    checks: list[DiagnosticCheck]


def _check(
    check_id: str,
    severity: str,
    state: str,
    evidence: dict[str, Any],
    remediation: str | None,
) -> DiagnosticCheck:
    return {
        "check_id": check_id,
        "severity": severity,
        "state": state,
        "evidence": evidence,
        "remediation_command": remediation,
    }


def _safe_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _mutation_evidence(home: Path) -> dict[str, Any] | None:
    newest: tuple[float, dict[str, Any]] | None = None
    for path in (home / "runs").glob("**/*.jsonl") if (home / "runs").is_dir() else ():
        try:
            rows = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in rows:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            event = str(row.get("event") or row.get("event_type") or "")
            if "mutation" not in event:
                continue
            stamp = path.stat().st_mtime
            proof = {
                "event": event,
                "timestamp": row.get("ts") or row.get("timestamp"),
                "accepted": row.get("accepted", row.get("ok")),
            }
            if newest is None or stamp >= newest[0]:
                newest = (stamp, proof)
    return newest[1] if newest else None


def _systemd_check(root: Path, home: Path) -> DiagnosticCheck:
    if not shutil.which("systemctl"):
        return _check(
            "systemd_consistency",
            "warning",
            "degraded",
            {"available": False},
            "singular config root install-systemd",
        )
    try:
        result = subprocess.run(
            [
                "systemctl",
                "show",
                "singular.service",
                "--property=Environment",
                "--value",
            ],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        result = None
    output = result.stdout if result is not None else ""
    consistent = (
        result is not None
        and result.returncode == 0
        and str(root) in output
        and str(home) in output
    )
    return _check(
        "systemd_consistency",
        "warning",
        "ready" if consistent else "degraded",
        {"unit": "singular.service", "context_matches": consistent},
        None if consistent else "singular config root install-systemd",
    )


def autonomous_diagnostics(
    *, run_generation: bool = False
) -> AutonomousDiagnosticReport:
    """Run ordered autonomous-readiness checks and return a stable payload."""

    from singular.governance.policy import load_circuit_state
    from singular.lives import load_registry
    from singular.providers import doctor_providers
    from singular.root_config import diagnose_registry_root

    checks: list[DiagnosticCheck] = []
    root_info = diagnose_registry_root()
    root = root_info["root"]
    root_ok = root.is_dir()
    checks.append(
        _check(
            "root_resolution",
            "critical",
            "ready" if root_ok else "blocked",
            {"source": root_info["source"], "exists": root_ok, "path": str(root)},
            None if root_ok else f"mkdir -p {root}",
        )
    )

    try:
        registry = load_registry()
    except (OSError, ValueError, json.JSONDecodeError):
        registry = {"active": None, "lives": {}}
    active = registry.get("active")
    meta = registry.get("lives", {}).get(active) if active else None
    home = Path(
        os.environ.get("SINGULAR_HOME")
        or getattr(meta, "path", root / "lives" / str(active or ""))
    )
    life_ok = bool(active and home.is_dir())
    checks.append(
        _check(
            "active_life",
            "critical",
            "ready" if life_ok else "blocked",
            {"configured": bool(active), "exists": home.is_dir(), "life": active},
            None if life_ok else "singular lives use <vie>",
        )
    )

    required = [home / "mem", home / "runs"]
    writable = life_ok and all(
        path.is_dir() and os.access(path, os.W_OK | os.X_OK) for path in required
    )
    checks.append(
        _check(
            "directory_permissions",
            "critical",
            "ready" if writable else "blocked",
            {"required": [p.name for p in required], "writable": writable},
            (
                None
                if writable
                else f"mkdir -p {home / 'mem'} {home / 'runs'} && chmod u+rwx {home / 'mem'} {home / 'runs'}"
            ),
        )
    )
    checks.append(_systemd_check(root, home))

    configured_name = (os.environ.get("LLM_PROVIDER") or "").strip()
    configured = bool(configured_name)
    checks.append(
        _check(
            "provider_configured",
            "critical",
            "ready" if configured else "blocked",
            {"configured": configured, "provider": configured_name or None},
            None if configured else "singular config providers doctor",
        )
    )
    provider_result = doctor_providers([configured_name])[0] if configured else None
    model_ready = bool(
        provider_result
        and provider_result.get("ok")
        and provider_result.get("llm_real")
    )
    checks.append(
        _check(
            "model_available",
            "critical",
            "ready" if model_ready else "blocked",
            {
                "provider": configured_name or None,
                "reachable": bool(provider_result and provider_result.get("reachable")),
                "category": (
                    provider_result.get("error_category")
                    if provider_result
                    else "not_configured"
                ),
            },
            (
                None
                if model_ready
                else (provider_result or {}).get("configuration_command")
                or "singular config providers doctor"
            ),
        )
    )

    generated = False
    generation_error: str | None = None
    if run_generation and model_ready:
        try:
            from singular.providers import _load_provider_contract

            contract = _load_provider_contract(configured_name)
            generated = bool(
                contract and contract.generate("Répondez uniquement: ok", timeout=2.0)
            )
        except (
            Exception
        ) as exc:  # diagnostic boundary: expose category, never message/secrets
            generation_error = type(exc).__name__
    generation_state = "ready" if (not run_generation or generated) else "degraded"
    checks.append(
        _check(
            "minimal_generation",
            "warning",
            generation_state,
            {
                "requested": run_generation,
                "succeeded": generated if run_generation else None,
                "error_category": generation_error,
            },
            None if generation_state == "ready" else "singular config providers doctor",
        )
    )

    circuit = load_circuit_state(home)
    closed = circuit.get("state") == "closed"
    checks.append(
        _check(
            "circuit_breaker",
            "critical",
            "ready" if closed else "blocked",
            {"state": circuit.get("state"), "updated_at": circuit.get("updated_at")},
            (
                None
                if closed
                else "singular governance recover --operator <nom> --justification <raison>"
            ),
        )
    )
    mutation = _mutation_evidence(home)
    checks.append(
        _check(
            "last_mutation",
            "warning",
            "ready" if mutation else "degraded",
            mutation or {"found": False},
            None if mutation else "singular loop --budget-seconds 60",
        )
    )

    psyche = _safe_json(home / "mem" / "psyche.json")
    narrative = _safe_json(home / "mem" / "self_narrative.json")
    pv, nv = psyche.get("psyche_version"), narrative.get("psyche_version")
    coherent = bool(psyche and narrative and pv == nv)
    checks.append(
        _check(
            "psyche_narrative_coherence",
            "critical",
            "ready" if coherent else "blocked",
            {
                "psyche_present": bool(psyche),
                "narrative_present": bool(narrative),
                "versions_match": pv == nv if psyche and narrative else False,
            },
            None if coherent else "singular self-narrative summarize",
        )
    )

    status = (
        "blocked"
        if any(c["state"] == "blocked" for c in checks)
        else ("degraded" if any(c["state"] == "degraded" for c in checks) else "ready")
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "exit_code": {"ready": READY, "degraded": DEGRADED, "blocked": BLOCKED}[status],
        "checks": checks,
    }
