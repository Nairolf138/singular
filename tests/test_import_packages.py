"""Smoke tests for the public modules shipped in the installable package."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


PUBLIC_MODULES = (
    "graine",
    "singular",
    "singular.cli",
    "singular.core.agent_runtime",
    "singular.action.sandbox_runner",
    "singular.interaction.tts_engine",
    "singular.mind.state_model",
    "singular.observability.audit_log",
    "singular.perception.audio.pipeline",
    "singular.perception.os.pipeline",
    "singular.perception.vision.pipeline",
    "singular.security.immune_response",
    "singular.security.policy_engine",
)


def test_source_package_imports_public_runtime_modules() -> None:
    root = Path(__file__).resolve().parent.parent
    src = root / "src"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(src)
    imports = "; ".join(f"import {module}" for module in PUBLIC_MODULES)

    result = subprocess.run(
        [sys.executable, "-c", imports],
        capture_output=True,
        text=True,
        cwd=root.parent,
        env=env,
    )
    assert result.returncode == 0, result.stderr
