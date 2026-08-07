import ast
import json
import subprocess

import pytest

import singular.life.sandbox as sandbox
from singular.life.sandbox import SandboxConfig, SandboxError, run


@pytest.fixture
def isolated_runtime(monkeypatch):
    """Model a runtime without requiring a container daemon in unit tests."""
    monkeypatch.setattr(sandbox.shutil, "which", lambda name: f"/usr/bin/{name}")

    def fake_run(command, **kwargs):
        if command[1] == "info":
            return subprocess.CompletedProcess(command, 0, '["name=seccomp"]', "")
        code = kwargs["input"]
        if "while True" in code:
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])
        if "300 * 1024" in code:
            payload = {"status": "error", "type": "MemoryError", "message": ""}
        else:
            env = {"__builtins__": sandbox.__dict__["__builtins__"]}
            # These snippets have already passed validation; this emulates only
            # the container protocol, not its security boundary.
            try:
                exec(compile(code, "<test-container>", "exec"), env, env)
                if "result" not in env:
                    raise RuntimeError("sandbox code did not set a result")
                payload = {"status": "result", "payload": env["result"]}
            except Exception as exc:
                payload = {
                    "status": "error",
                    "type": type(exc).__name__,
                    "message": str(exc),
                }
        return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")

    monkeypatch.setattr(sandbox.subprocess, "run", fake_run)


def test_basic_execution(isolated_runtime):
    assert run("result = max(1, 2)") == 2


def test_missing_result_raises_sandbox_error(isolated_runtime):
    with pytest.raises(SandboxError, match="result"):
        run("value = 1")


@pytest.mark.parametrize(
    "code", ["import os", 'open("foo")', "import socket", "import subprocess"]
)
def test_forbidden_names_and_imports(code):
    with pytest.raises(SandboxError):
        run(code)


@pytest.mark.parametrize(
    "attribute",
    [
        "__class__",
        "__mro__",
        "__base__",
        "__subclasses__",
        "__globals__",
        "__builtins__",
        "__getattribute__",
        "__dict__",
        "_private",
    ],
)
def test_object_introspection_attributes_are_rejected(attribute):
    with pytest.raises(SandboxError, match="private attribute"):
        sandbox._validate_ast(ast.parse(f"result = value.{attribute}"))


def test_builtin_recovery_chain_is_rejected():
    code = "result = ().__class__.__base__.__subclasses__()"
    with pytest.raises(SandboxError):
        run(code)


def test_timeout(isolated_runtime):
    with pytest.raises(TimeoutError):
        run("while True: pass", timeout=0.1)


def test_memory_limit(isolated_runtime):
    with pytest.raises(MemoryError):
        run("result = 'x' * (300 * 1024 * 1024)")


def test_container_has_all_required_system_isolation(isolated_runtime, monkeypatch):
    commands = []
    original = sandbox.subprocess.run

    def record(command, **kwargs):
        commands.append(command)
        return original(command, **kwargs)

    monkeypatch.setattr(sandbox.subprocess, "run", record)
    assert run("result = 1") == 1
    command = commands[-1]
    for expected in (
        "--network=none",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--pids-limit=32",
        "--user=65534:65534",
        "--cpus=1",
    ):
        assert expected in command
    assert any(value.startswith("--memory=") for value in command)
    assert any(value.startswith("--ulimit=cpu=") for value in command)
    assert any(
        value.startswith("--tmpfs=/tmp:rw,noexec,nosuid,nodev") for value in command
    )


@pytest.mark.parametrize(
    "attack",
    [
        'result = open("/etc/passwd").read()',  # host files
        "import socket\nresult = socket.socket()",  # network
        "import subprocess\nresult = subprocess.run(['id'])",  # processes
    ],
)
def test_adversarial_io_is_rejected_before_execution(attack):
    with pytest.raises(SandboxError):
        run(attack)


def test_sandbox_rejects_enabled_network_policy():
    with pytest.raises(SandboxError, match="only supports disabled"):
        sandbox._command("docker", SandboxConfig(network_policy="host"))


def test_sandbox_network_policy_defaults_to_none(monkeypatch):
    monkeypatch.delenv("SINGULAR_SANDBOX_NETWORK_POLICY", raising=False)
    assert SandboxConfig.from_environment().network_policy == "none"


def test_refuses_platform_without_resource_limits(monkeypatch):
    monkeypatch.setattr(sandbox, "resource_module", None)
    with pytest.raises(SandboxError, match="resource limits"):
        run("result = 1")


def test_refuses_runtime_without_seccomp(monkeypatch):
    monkeypatch.setattr(sandbox.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(
        sandbox.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0], 0, '["apparmor"]', ""
        ),
    )
    with pytest.raises(SandboxError, match="seccomp"):
        run("result = 1")


def test_refuses_missing_container_runtime(monkeypatch):
    monkeypatch.setattr(sandbox.shutil, "which", lambda _name: None)
    with pytest.raises(SandboxError, match="podman or docker"):
        run("result = 1")
