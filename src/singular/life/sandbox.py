"""Functional validation and system-isolated execution of untrusted snippets.

The AST checks in this module are defence in depth.  They are deliberately not
treated as a security boundary; that boundary is an OCI container runtime.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
import json
import math
import os
import shutil
import subprocess
import sys
from typing import Any

try:
    import resource as resource_module
except ImportError:  # pragma: no cover - unsupported platforms
    resource_module = None


ALLOWED_BUILTINS = (
    "abs",
    "min",
    "max",
    "range",
    "len",
    "sum",
    "all",
    "any",
    "float",
)
FORBIDDEN_NAMES = {
    "open",
    "exec",
    "eval",
    "compile",
    "__import__",
    "input",
    "os",
    "sys",
    "socket",
    "subprocess",
}
FORBIDDEN_NODES = (ast.Import, ast.ImportFrom, ast.With, ast.AsyncWith)

DEFAULT_TIMEOUT_S = 3.0
MIN_TIMEOUT_S = 0.05
DEFAULT_STARTUP_GRACE_S = 2.0
DEFAULT_MEMORY_LIMIT = 256 * 1024 * 1024
DEFAULT_IMAGE = "python:3.11-alpine"


class SandboxError(RuntimeError):
    """Raised when validation fails or secure isolation is unavailable."""


@dataclass(frozen=True)
class SandboxConfig:
    execution_timeout_s: float = DEFAULT_TIMEOUT_S
    startup_grace_s: float = DEFAULT_STARTUP_GRACE_S
    min_timeout_s: float = MIN_TIMEOUT_S
    memory_limit: int = DEFAULT_MEMORY_LIMIT
    multiprocessing_method: str | None = None  # retained for API compatibility
    runtime: str | None = None
    image: str = DEFAULT_IMAGE
    network_policy: str = "none"

    @classmethod
    def from_environment(
        cls, *, timeout: float | None = None, memory_limit: int | None = None
    ) -> "SandboxConfig":
        return cls(
            execution_timeout_s=max(
                float(
                    timeout
                    if timeout is not None
                    else os.getenv("SINGULAR_SANDBOX_TIMEOUT", DEFAULT_TIMEOUT_S)
                ),
                float(os.getenv("SINGULAR_SANDBOX_MIN_TIMEOUT", MIN_TIMEOUT_S)),
            ),
            startup_grace_s=float(
                os.getenv("SINGULAR_SANDBOX_STARTUP_GRACE", DEFAULT_STARTUP_GRACE_S)
            ),
            min_timeout_s=float(
                os.getenv("SINGULAR_SANDBOX_MIN_TIMEOUT", MIN_TIMEOUT_S)
            ),
            memory_limit=int(
                memory_limit
                if memory_limit is not None
                else os.getenv("SINGULAR_SANDBOX_MEMORY_LIMIT", DEFAULT_MEMORY_LIMIT)
            ),
            runtime=os.getenv("SINGULAR_SANDBOX_RUNTIME") or None,
            image=os.getenv("SINGULAR_SANDBOX_IMAGE", DEFAULT_IMAGE),
            network_policy=os.getenv("SINGULAR_SANDBOX_NETWORK_POLICY", "none").strip().lower(),
        )


def _validate_ast(tree: ast.AST) -> None:
    """Apply functional restrictions (not a security boundary)."""
    for node in ast.walk(tree):
        if isinstance(node, FORBIDDEN_NODES):
            raise SandboxError("forbidden syntax detected")
        if isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            raise SandboxError(f"use of '{node.id}' is forbidden")
        if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            raise SandboxError(
                f"access to private attribute '{node.attr}' is forbidden"
            )


def _runtime(configured: str | None) -> str:
    if sys.platform != "linux" or resource_module is None:
        raise SandboxError(
            "secure sandbox unavailable: Linux resource limits are required"
        )
    candidate = configured or shutil.which("podman") or shutil.which("docker")
    if not candidate or not shutil.which(candidate):
        raise SandboxError("secure sandbox unavailable: podman or docker is required")
    try:
        probe = subprocess.run(
            [candidate, "info", "--format", "{{json .SecurityOptions}}"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SandboxError(
            "secure sandbox unavailable: container runtime probe failed"
        ) from exc
    security = (probe.stdout + probe.stderr).lower()
    if probe.returncode or "seccomp" not in security:
        raise SandboxError(
            "secure sandbox unavailable: an active seccomp profile is required"
        )
    return candidate


_CONTAINER_WORKER = r"""
import builtins, json, sys
code = sys.stdin.read()
allowed_names = __ALLOWED_BUILTINS__
env = {"__builtins__": {name: getattr(builtins, name) for name in allowed_names}}
try:
    exec(compile(code, "<sandbox>", "exec"), env, env)
    if "result" not in env:
        raise RuntimeError("sandbox code did not set a result")
    print(json.dumps({"status": "result", "payload": env["result"]}))
except BaseException as exc:
    print(json.dumps({"status": "error", "type": type(exc).__name__, "message": str(exc)}))
""".replace("__ALLOWED_BUILTINS__", repr(ALLOWED_BUILTINS))


def _command(runtime: str, config: SandboxConfig) -> list[str]:
    if config.network_policy not in {"none", "disabled"}:
        raise SandboxError(
            "untrusted-code sandbox only supports disabled system networking"
        )
    cpu_seconds = max(1, math.ceil(config.execution_timeout_s))
    return [
        runtime,
        "run",
        "--rm",
        "-i",
        "--pull=never",
        "--network=none",
        "--user=65534:65534",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--pids-limit=32",
        f"--memory={config.memory_limit}",
        "--cpus=1",
        f"--ulimit=cpu={cpu_seconds}:{cpu_seconds}",
        "--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=16777216,mode=700,uid=65534,gid=65534",
        "--workdir=/tmp",
        config.image,
        "python",
        "-I",
        "-c",
        _CONTAINER_WORKER,
    ]


def run(
    code: str,
    timeout: float | None = None,
    memory_limit: int | None = None,
    *,
    config: SandboxConfig | None = None,
) -> Any:
    """Validate *code*, then execute it inside a locked-down OCI container.

    Execution is refused rather than silently falling back to a local child
    process when the required Linux, resource-limit, runtime, and seccomp
    guarantees cannot be established.
    """
    _validate_ast(ast.parse(code, mode="exec"))
    policy = config or SandboxConfig.from_environment(
        timeout=timeout, memory_limit=memory_limit
    )
    runtime = _runtime(policy.runtime)
    try:
        completed = subprocess.run(
            _command(runtime, policy),
            input=code,
            capture_output=True,
            text=True,
            timeout=policy.startup_grace_s + policy.execution_timeout_s,
            check=False,
            env={"PATH": os.environ.get("PATH", "")},
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError("sandbox execution timed out") from exc
    if completed.returncode:
        raise SandboxError(
            f"isolated sandbox failed (exit {completed.returncode}): {completed.stderr.strip()}"
        )
    try:
        message = json.loads(completed.stdout.strip())
    except (json.JSONDecodeError, AttributeError) as exc:
        raise SandboxError("isolated sandbox returned an invalid response") from exc
    if message.get("status") == "result":
        return message.get("payload")
    error_type = message.get("type")
    detail = message.get("message", "sandbox execution failed")
    if error_type == "MemoryError":
        raise MemoryError(detail)
    if error_type == "RuntimeError" and "did not set a result" in detail:
        raise SandboxError(detail)
    raise SandboxError(f"sandboxed code raised {error_type}: {detail}")
