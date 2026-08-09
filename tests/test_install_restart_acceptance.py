"""Acceptance coverage for an installed orchestrator restart, without systemd."""

from __future__ import annotations

import json
import os
import pwd
import grp
import shlex
from pathlib import Path

import pytest

from singular import cli


def _read_environment_file(path: Path) -> dict[str, str]:
    """Read the small EnvironmentFile subset emitted by the installer."""

    if not path.is_file():
        raise AssertionError(
            f"fichier d’environnement manquant: {path}; relancez "
            "`singular config root install-systemd`"
        )
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        name, raw_value = line.split("=", 1)
        parsed = shlex.split(raw_value, posix=True)
        values[name] = parsed[0] if parsed else ""
    return values


def _read_unit(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.startswith("["):
            name, value = line.split("=", 1)
            values[name] = value
    return values


@pytest.mark.integration
def test_installed_service_restarts_the_selected_life_with_existing_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Build, inspect and boot a complete installation twice in isolation."""

    root = tmp_path / "installed-state"
    binary = tmp_path / "bin" / "singular"
    environment_file = tmp_path / "etc" / "singular.env"
    unit_file = tmp_path / "systemd" / "singular.service"
    binary.parent.mkdir()
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    binary.chmod(0o755)
    account = pwd.getpwuid(os.getuid())
    group = grp.getgrgid(account.pw_gid)
    systemctl_calls: list[list[str]] = []
    monkeypatch.setattr(
        cli.subprocess,
        "run",
        lambda command, check: systemctl_calls.append(command),
    )
    # Register both variables with monkeypatch before CLI pre-parsing mutates
    # them, so this acceptance scenario cannot leak its installation context.
    monkeypatch.setenv("SINGULAR_ROOT", str(root))
    monkeypatch.delenv("SINGULAR_HOME", raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "ollama")

    assert cli.main(["--root", str(root), "lives", "create", "--name", "Ada"]) == 0
    assert cli.main(["--root", str(root), "lives", "use", "ada"]) == 0
    # The service contract includes both writable state paths; ``runs`` is
    # normally materialised by the first foreground run.
    (root / "lives" / "ada" / "runs").mkdir()
    assert (
        cli.main(
            [
                "--root",
                str(root),
                "config",
                "root",
                "install-systemd",
                "--user",
                account.pw_name,
                "--group",
                group.gr_name,
                "--binary",
                str(binary),
                "--environment-file",
                str(environment_file),
                "--unit-file",
                str(unit_file),
            ]
        )
        == 0
    )

    unit = _read_unit(unit_file)
    environment = _read_environment_file(environment_file)
    life_home = (root / "lives" / "ada").resolve()
    assert unit["ExecStart"] == f"{binary.resolve()} orchestrate run"
    assert unit["WorkingDirectory"] == str(life_home)
    assert Path(unit["EnvironmentFile"]) == environment_file.resolve()
    assert environment == {
        "SINGULAR_ROOT": str(root.resolve()),
        "SINGULAR_HOME": str(life_home),
        "LLM_PROVIDER": "ollama",
    }
    assert systemctl_calls == [["systemctl", "daemon-reload"]]

    starts: list[dict[str, object]] = []

    def fake_daemon(**_kwargs: object) -> int:
        state_path = Path(os.environ["SINGULAR_HOME"]) / "mem" / "acceptance.json"
        existing = json.loads(state_path.read_text()) if state_path.exists() else None
        starts.append(
            {
                "root": os.environ["SINGULAR_ROOT"],
                "home": os.environ["SINGULAR_HOME"],
                "provider": os.environ["LLM_PROVIDER"],
                "existing": existing,
                "cwd": str(Path.cwd()),
            }
        )
        if existing is None:
            state_path.write_text(json.dumps({"generation": 1}), encoding="utf-8")
        return 0

    monkeypatch.setattr("singular.orchestrator.run_orchestrator_daemon", fake_daemon)
    registry_before = (root / "lives" / "registry.json").read_bytes()
    for _ in range(2):
        monkeypatch.delenv("SINGULAR_HOME", raising=False)
        monkeypatch.delenv("SINGULAR_ROOT", raising=False)
        for name, value in environment.items():
            monkeypatch.setenv(name, value)
        assert cli.main(shlex.split(unit["ExecStart"])[1:]) == 0

    assert starts[0]["existing"] is None
    assert starts[1]["existing"] == {"generation": 1}
    assert all(start["root"] == str(root.resolve()) for start in starts)
    assert all(start["home"] == str(life_home) for start in starts)
    assert all(start["provider"] == "ollama" for start in starts)
    assert all(start["cwd"] != start["home"] for start in starts)
    assert (root / "lives" / "registry.json").read_bytes() == registry_before
    assert len(list((root / "lives").glob("*/id.json"))) == 1


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        ("permissions", "corrigez avec `chown -R"),
        ("active", "exécutez `singular lives use <vie>`"),
        ("binary", "binaire singular introuvable"),
    ],
)
def test_install_failures_give_precise_remediation(
    failure: str,
    expected: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / "root"
    life = root / "lives" / "ada"
    (life / "mem").mkdir(parents=True)
    (life / "runs").mkdir()
    binary = tmp_path / "singular"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    account = pwd.getpwuid(os.getuid())
    group = grp.getgrgid(account.pw_gid)
    if failure == "permissions":
        monkeypatch.setattr(cli, "_service_user_can_write", lambda *_args: False)
    selected_life = None if failure == "active" else life
    selected_binary = tmp_path / "missing" if failure == "binary" else binary

    result = cli._install_systemd_service(
        root,
        selected_life,
        user=account.pw_name,
        group=group.gr_name,
        binary=selected_binary,
        environment_file=tmp_path / "singular.env",
        unit_file=tmp_path / "singular.service",
    )

    assert result == 1
    assert expected in capsys.readouterr().err


def test_missing_environment_file_gives_reinstall_remediation(tmp_path: Path) -> None:
    with pytest.raises(AssertionError, match="relancez.*install-systemd"):
        _read_environment_file(tmp_path / "missing.env")
