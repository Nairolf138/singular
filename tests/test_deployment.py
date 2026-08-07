import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.check_deployment_manifests import main as check_manifests
from singular.cli import main


def test_deployment_manifests_are_complete() -> None:
    assert check_manifests() == 0


@pytest.mark.integration
def test_injected_restart_preserves_identity_and_progress(tmp_path: Path) -> None:
    """Run any injected supervisor command twice against an existing data root."""
    root = tmp_path / "state"
    assert main(["--root", str(root), "lives", "create", "--name", "Resume"]) == 0
    identity_path = root / "lives" / "resume" / "id.json"
    progress_path = root / "lives" / "resume" / "mem" / "restart-progress.json"
    progress = {"completed_steps": 7, "checkpoint": "before-restart"}
    progress_path.write_text(json.dumps(progress), encoding="utf-8")
    identity = identity_path.read_bytes()

    template = os.environ.get(
        "SINGULAR_INTEGRATION_COMMAND",
        f"{shlex.quote(sys.executable)} -m singular --root {{root}} status --format json",
    )
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).parents[1] / "src")}
    for _ in range(2):
        command = template.format(root=shlex.quote(str(root)))
        subprocess.run(shlex.split(command), check=True, env=env, timeout=30)

    assert identity_path.read_bytes() == identity
    assert json.loads(progress_path.read_text(encoding="utf-8")) == progress
