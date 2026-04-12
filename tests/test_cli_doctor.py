from pathlib import Path
import types

import singular.cli as cli
from singular.lives import load_registry


def test_doctor_reports_status_and_powershell_fix(monkeypatch, capsys) -> None:
    scripts_dir = Path("/tmp/singular-user-scripts")
    monkeypatch.setattr(cli.sys, "executable", "/tmp/python/bin/python")
    monkeypatch.setattr(
        cli.sysconfig,
        "get_path",
        lambda *_args, **_kwargs: str(scripts_dir),
    )
    monkeypatch.setenv("PATH", "/usr/bin:/bin")

    cli.main(["doctor"])

    out = capsys.readouterr().out
    assert "Diagnostic Singular" in out
    assert "- Scripts dans PATH      : non" in out
    assert "SetEnvironmentVariable" in out
    assert "Get-Command singular" in out


def test_doctor_confirms_when_scripts_are_in_path(monkeypatch, capsys) -> None:
    scripts_dir = Path("/tmp/singular-user-scripts")
    monkeypatch.setattr(cli.sys, "executable", "/tmp/python/bin/python")
    monkeypatch.setattr(
        cli.sysconfig,
        "get_path",
        lambda *_args, **_kwargs: str(scripts_dir),
    )
    monkeypatch.setenv("PATH", f"/usr/bin:{scripts_dir}")

    cli.main(["doctor"])

    out = capsys.readouterr().out
    assert "- Scripts dans PATH      : oui" in out
    assert "PATH semble correctement configuré" in out


def test_doctor_fix_calls_windows_path_update_when_missing(monkeypatch, capsys) -> None:
    scripts_dir = Path("/tmp/singular-user-scripts")
    monkeypatch.setattr(cli.sys, "executable", "/tmp/python/bin/python")
    monkeypatch.setattr(
        cli.sysconfig,
        "get_path",
        lambda *_args, **_kwargs: str(scripts_dir),
    )
    monkeypatch.setenv("PATH", "/usr/bin:/bin")

    called: list[Path] = []

    def fake_fix(path: Path) -> bool:
        called.append(path)
        return True

    monkeypatch.setattr(cli, "_doctor_fix_windows_user_path", fake_fix)

    cli.main(["doctor", "--fix"])

    out = capsys.readouterr().out
    assert "Application du correctif automatique (`--fix`)…" in out
    assert called == [scripts_dir.resolve()]


def test_doctor_fix_windows_user_path_is_idempotent(monkeypatch, capsys) -> None:
    scripts_dir = Path(r"C:\Users\Ada\AppData\Roaming\Python\Python313\Scripts")
    monkeypatch.setattr(cli.os, "name", "nt")

    store: dict[str, str] = {"Path": f"{scripts_dir};C:\\Windows\\System32"}

    class _FakeKey:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    fake_winreg = types.SimpleNamespace(
        HKEY_CURRENT_USER=1,
        KEY_READ=0x20019,
        KEY_SET_VALUE=0x0002,
        REG_EXPAND_SZ=2,
        OpenKey=lambda *_args, **_kwargs: _FakeKey(),
        QueryValueEx=lambda _key, value_name: (store[value_name], 1),
        SetValueEx=lambda _key, value_name, *_args: store.__setitem__(
            value_name, _args[-1]
        ),
    )
    monkeypatch.setitem(cli.sys.modules, "winreg", fake_winreg)

    changed = cli._doctor_fix_windows_user_path(scripts_dir)
    out = capsys.readouterr().out

    assert changed is False
    assert store["Path"] == f"{scripts_dir};C:\\Windows\\System32"
    assert "déjà présent" in out


def test_quickstart_creates_life_without_prompt_when_not_tty(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SINGULAR_ROOT", str(tmp_path))
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: False)

    exit_code = cli.main(["quickstart", "--name", "Starter"])
    assert exit_code == 0

    registry = load_registry()
    assert registry["active"] is not None
    active = registry["active"]
    assert registry["lives"][active].name == "Starter"


def test_monitor_uses_guided_verbose_prompt(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SINGULAR_ROOT", str(tmp_path))
    monkeypatch.delenv("SINGULAR_HOME", raising=False)
    cli.main(["lives", "create", "--name", "Alpha"])

    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: True)
    answers = iter(["o"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))

    called: dict[str, object] = {}

    def fake_status(*, verbose: bool = False, output_format: str = "plain") -> None:
        called["verbose"] = verbose
        called["output_format"] = output_format

    monkeypatch.setattr("singular.organisms.status.status", fake_status)

    cli.main(["--format", "table", "monitor"])
    assert called == {"verbose": True, "output_format": "table"}
