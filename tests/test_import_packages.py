import os
import subprocess
import sys
from pathlib import Path


def test_editable_install_imports_graine_and_singular() -> None:
    root = Path(__file__).resolve().parent.parent
    src = root / "src"
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{src}{os.pathsep}" + env.get("PYTHONPATH", "")

    result = subprocess.run(
        [sys.executable, "-c", "import graine; import singular"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, result.stderr
