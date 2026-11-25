"""Validate runtime resources from an installed wheel, outside the checkout."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_installed_wheel_contains_all_runtime_resources(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    wheelhouse = tmp_path / "wheelhouse"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            ".",
            "--no-deps",
            "-w",
            str(wheelhouse),
        ],
        cwd=repo_root,
        check=True,
    )
    wheel = next(wheelhouse.glob("singular-*.whl"))

    venv = tmp_path / "venv"
    subprocess.run(
        [sys.executable, "-m", "venv", "--system-site-packages", str(venv)],
        check=True,
    )
    python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    subprocess.run(
        [python, "-m", "pip", "install", "--no-deps", "--force-reinstall", str(wheel)],
        check=True,
    )

    execution_dir = tmp_path / "installed-runtime"
    execution_dir.mkdir()
    script = r"""
from importlib.resources import as_file, files
from pathlib import Path

from singular.life.ecosystem import EcosystemRulesConfig
from singular.life.life_definition import load_life_definition_config
from singular.orchestrator.lifecycle_clock import load_lifecycle_clock_config
from singular.organisms.birth import _load_starter_profiles, birth
from singular.resources import config_resource
from singular.sensors.config import load_host_sensor_thresholds
from graine.evolver.dsl import OPERATOR_NAMES
from graine.evolver.generate import load_zones

home = Path("life")
birth(seed=1, home=home, name="Wheel Life")
assert (home / "id.json").is_file()
assert _load_starter_profiles()["assistant"]
assert (home / "skills" / "validation.py").is_file()
assert (home / "skills" / "metrics.py").is_file()
assert load_host_sensor_thresholds().cpu_warning_percent == 85.0
assert OPERATOR_NAMES
assert load_zones()
assert load_lifecycle_clock_config().cycle.veille_seconds == 2.0
assert config_resource("life_definition.yaml").is_file()
assert load_life_definition_config().statuses["running"] == "running"
for mode in ("lab", "production"):
    with as_file(config_resource("ecosystem", f"{mode}.json")) as config_path:
        config = EcosystemRulesConfig.from_file(config_path)
    assert config.resource_competition_unit > 0

dashboard = files("singular").joinpath("dashboard")
assert dashboard.joinpath("templates", "dashboard.html").is_file()
assert dashboard.joinpath("templates", "mutation_detail.html").is_file()
assert dashboard.joinpath("static", "dashboard.css").is_file()
"""
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    subprocess.run([python, "-c", script], cwd=execution_dir, env=env, check=True)
    root = execution_dir / "registry"
    for arguments in (
        ("lives", "create", "--name", "Wheel Life", "--starter-profile", "assistant"),
        ("lives", "use", "wheel-life"),
        ("status", "--format", "table"),
        ("talk", "--prompt", "Bonjour"),
        ("doctor",),
        ("retention", "status"),
        ("retention", "run", "--dry-run"),
    ):
        subprocess.run(
            [python, "-m", "singular", *arguments],
            cwd=execution_dir,
            env={**env, "SINGULAR_ROOT": str(root)},
            check=True,
            capture_output=True,
            text=True,
        )
