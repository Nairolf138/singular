import ast
import builtins
import os
import sys
from pathlib import Path

# Ensure src directory is on sys.path for package imports during testing
src_path = Path(__file__).resolve().parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

# Expose the FastAPI stub only when tests explicitly select the lightweight mode.
# This decision is made here, before any test can import ``singular.dashboard``.
tests_path = Path(__file__).resolve().parent
fastapi_mode = os.environ.get("SINGULAR_TEST_FASTAPI", "stub")
if fastapi_mode not in {"stub", "real"}:
    raise RuntimeError("SINGULAR_TEST_FASTAPI must be either 'stub' or 'real'")

if fastapi_mode == "stub":
    if str(tests_path) not in sys.path:
        sys.path.insert(0, str(tests_path))

    import fastapi_stub  # noqa: E402
    import fastapi_stub.responses  # noqa: E402,F401 - imported for side effect
    import fastapi_stub.staticfiles  # noqa: E402,F401 - imported for side effect
    import fastapi_stub.testclient  # noqa: E402,F401 - imported for side effect

    sys.modules.setdefault("fastapi", fastapi_stub)
    sys.modules.setdefault("fastapi.responses", fastapi_stub.responses)
    sys.modules.setdefault("fastapi.staticfiles", fastapi_stub.staticfiles)
    sys.modules.setdefault("fastapi.testclient", fastapi_stub.testclient)

import pytest  # noqa: E402

from singular.life.checkpointing import Checkpoint, save_checkpoint  # noqa: E402
from singular.life import sandbox as life_sandbox  # noqa: E402
from singular.memory_layers.local_json import LocalJsonMemoryBackend  # noqa: E402
from singular.memory_layers.service import MemoryLayerService  # noqa: E402


@pytest.fixture
def local_sandbox(monkeypatch):
    """Emulate the trusted worker protocol without starting an OCI container."""

    def execute(code):
        life_sandbox._validate_ast(ast.parse(code, mode="exec"))
        namespace = {"__builtins__": vars(builtins)}
        exec(compile(code, "<unit-sandbox>", "exec"), namespace, namespace)
        if "result" not in namespace:
            raise life_sandbox.SandboxError("sandbox code did not set a result")
        return namespace["result"]

    monkeypatch.setattr(life_sandbox, "run", execute)
    return execute


@pytest.fixture
def isolated_singular_home(tmp_path, monkeypatch):
    """Create an isolated SINGULAR_HOME with lightweight life directories."""

    root = tmp_path / "life"
    (root / "skills").mkdir(parents=True)
    (root / "mem").mkdir()
    (root / "runs").mkdir()
    monkeypatch.setenv("SINGULAR_HOME", str(root))
    return root


@pytest.fixture
def temp_skills_dir(isolated_singular_home):
    """Return a small skills/ directory containing one mutable Python skill."""

    skills_dir = isolated_singular_home / "skills"
    (skills_dir / "skill.py").write_text("result = 2\n", encoding="utf-8")
    return skills_dir


@pytest.fixture
def temp_checkpoint(isolated_singular_home):
    """Create and return a checkpoint path for lifecycle tests."""

    checkpoint_path = isolated_singular_home / "life_checkpoint.json"
    save_checkpoint(checkpoint_path, Checkpoint())
    return checkpoint_path


@pytest.fixture
def isolated_memory(isolated_singular_home):
    """Return an isolated memory-layer service and backend pair."""

    memory_dir = isolated_singular_home / "mem" / "layers"
    backend = LocalJsonMemoryBackend(memory_dir)
    service = MemoryLayerService(backend, short_term_window=5, consolidate_every=2)
    return service, backend, memory_dir


@pytest.fixture
def temp_life(isolated_singular_home, temp_skills_dir, temp_checkpoint):
    """Return lightweight paths for a temporary life."""

    return {
        "root": isolated_singular_home,
        "skills_dir": temp_skills_dir,
        "checkpoint_path": temp_checkpoint,
        "mem_dir": isolated_singular_home / "mem",
    }
