import json
from pathlib import Path
import types

import singular.cli as cli


def test_config_openai_non_interactive_masks_output(monkeypatch, capsys) -> None:
    api_key = "sk-secretkey123456"
    monkeypatch.setattr(cli.os, "name", "posix")

    exit_code = cli.main(["config", "openai", "--api-key", api_key])

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "Clé OpenAI chargée" in out
    assert api_key not in out
    assert "sk-****" in out


def test_config_openai_interactive_uses_getpass(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli.os, "name", "posix")
    monkeypatch.setattr(cli.getpass, "getpass", lambda _prompt: "sk-from-getpass-1234")

    exit_code = cli.main(["config", "openai"])

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "sk-from-getpass-1234" not in out


def test_config_openai_empty_key_returns_error(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli.os, "name", "posix")

    exit_code = cli.main(["config", "openai", "--api-key", ""])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Clé API vide" in captured.err


def test_config_openai_windows_writes_hkcu_environment(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli.os, "name", "nt")
    store: dict[str, str] = {}

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
        SetValueEx=lambda _key, value_name, *_args: store.__setitem__(
            value_name, _args[-1]
        ),
    )
    monkeypatch.setitem(cli.sys.modules, "winreg", fake_winreg)

    raw_key = "sk-win-secret-123456"
    exit_code = cli.main(
        ["--home", "/tmp/singular-life", "config", "openai", "--api-key", raw_key]
    )

    out = capsys.readouterr().out
    assert exit_code == 0
    assert store["OPENAI_API_KEY"] == raw_key
    assert "HKCU\\Environment" in out
    assert "redémarrer PowerShell" in out
    assert raw_key not in out


def test_config_openai_shell_profile_append_with_confirmation(
    monkeypatch, tmp_path, capsys
) -> None:
    monkeypatch.setattr(cli.os, "name", "posix")
    monkeypatch.setattr("builtins.input", lambda _prompt: "OUI")
    profile = tmp_path / ".bashrc"

    raw_key = "sk-profile-secret-abcdef"
    exit_code = cli.main(
        [
            "config",
            "openai",
            "--api-key",
            raw_key,
            "--shell-profile",
            str(profile),
        ]
    )

    out = capsys.readouterr().out
    content = profile.read_text(encoding="utf-8")
    assert exit_code == 0
    assert "OPENAI_API_KEY" in content
    assert raw_key in content
    assert raw_key not in out


def test_config_openai_test_ping_success(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli.os, "name", "posix")
    monkeypatch.setattr(
        "singular.providers.llm_openai.generate_reply", lambda _prompt: "ok"
    )

    exit_code = cli.main(["config", "openai", "--api-key", "sk-test-ok-1234", "--test"])

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "Test OpenAI réussi" in out


def test_config_openai_test_ping_failure(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli.os, "name", "posix")
    monkeypatch.setattr(
        "singular.providers.llm_openai.generate_reply",
        lambda _prompt: "Error communicating with OpenAI.",
    )

    exit_code = cli.main(
        ["config", "openai", "--api-key", "sk-test-ko-1234", "--test"]
    )

    out = capsys.readouterr().out
    assert exit_code == 1
    assert "Test OpenAI échoué" in out


def test_config_root_set_global_persists_and_show_reads_it(
    monkeypatch, tmp_path, capsys
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(workspace)

    exit_code = cli.main(["config", "root", "set", "lab", "--scope", "global"])
    out_set = capsys.readouterr().out
    assert exit_code == 0
    assert "global" in out_set

    cfg_path = tmp_path / "home" / ".singular" / "config.json"
    payload = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert payload["registry_root"] == "lab"

    exit_code = cli.main(["config", "root", "show"])
    out_show = capsys.readouterr().out
    assert exit_code == 0
    assert str(tmp_path / "home" / ".singular" / "lab") in out_show


def test_config_root_set_project_overrides_global(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(workspace)

    assert cli.main(["config", "root", "set", "global-root", "--scope", "global"]) == 0
    capsys.readouterr()
    assert cli.main(["config", "root", "set", "project-root", "--scope", "project"]) == 0
    capsys.readouterr()

    exit_code = cli.main(["config", "root", "show"])
    out = capsys.readouterr().out
    assert exit_code == 0
    assert str(workspace / ".singular" / "project-root") in out


def test_implicit_registry_root_windows_uses_path_for_env_value(monkeypatch) -> None:
    monkeypatch.setattr(cli.os, "name", "nt")
    monkeypatch.setenv("SINGULAR_ROOT", r"C:\tmp\singular")

    root = cli._implicit_registry_root_from_env_or_default()

    assert isinstance(root, Path)
    assert root == Path(r"C:\tmp\singular").expanduser()


def test_implicit_registry_root_windows_defaults_to_user_home(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(cli.os, "name", "nt")
    monkeypatch.delenv("SINGULAR_ROOT", raising=False)
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))

    root = cli._implicit_registry_root_from_env_or_default()

    assert root == cli._HOST_PATH_CLS("~/.singular").expanduser()


def test_implicit_registry_root_posix_keeps_configured_behavior(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(cli.os, "name", "posix")
    monkeypatch.delenv("SINGULAR_ROOT", raising=False)
    configured = tmp_path / "configured-root"
    monkeypatch.setattr(cli, "load_configured_registry_root", lambda: configured)

    root = cli._implicit_registry_root_from_env_or_default()

    assert root == configured
