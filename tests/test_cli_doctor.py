from pathlib import Path

import singular.cli as cli


def test_doctor_reports_status_and_powershell_fix(
    monkeypatch, capsys
) -> None:
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


def test_doctor_confirms_when_scripts_are_in_path(
    monkeypatch, capsys
) -> None:
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
