import os
import sys
from pathlib import Path

# Ensure src directory is on sys.path for package imports during testing
src_path = Path(__file__).resolve().parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

# Expose the FastAPI stub and alias it as the real package
tests_path = Path(__file__).resolve().parent
if str(tests_path) not in sys.path:
    sys.path.insert(0, str(tests_path))

os.environ["PYTHONPATH"] = f"{tests_path}{os.pathsep}" + os.environ.get("PYTHONPATH", "")

import fastapi_stub
import fastapi_stub.responses  # noqa: F401 - imported for side effect
import fastapi_stub.testclient  # noqa: F401 - imported for side effect

sys.modules.setdefault("fastapi", fastapi_stub)
sys.modules.setdefault("fastapi.responses", fastapi_stub.responses)
sys.modules.setdefault("fastapi.testclient", fastapi_stub.testclient)
