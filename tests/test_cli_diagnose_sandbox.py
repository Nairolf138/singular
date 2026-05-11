from __future__ import annotations

from pathlib import Path

import singular.cli as cli


def _write_skill(home: Path, name: str, source: str) -> None:
    skills = home / "skills"
    skills.mkdir(parents=True, exist_ok=True)
    (skills / name).write_text(source, encoding="utf-8")


def test_diagnose_sandbox_reports_ok_skill(monkeypatch, tmp_path, capsys) -> None:
    home = tmp_path / "life"
    _write_skill(home, "ok.py", "result = 1\n")

    exit_code = cli.main(["--home", str(home), "diagnose", "sandbox"])

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "Diagnostic sandbox skills" in out
    assert "ok.py | OK | 1 | - | - | Aucune correction nécessaire." in out


def test_diagnose_sandbox_reports_missing_result(monkeypatch, tmp_path, capsys) -> None:
    home = tmp_path / "life"
    _write_skill(home, "missing.py", "value = 1\n")

    exit_code = cli.main(["--home", str(home), "diagnose", "sandbox"])

    out = capsys.readouterr().out
    assert exit_code == 1
    assert "missing.py | KO | - | missing_result" in out
    assert "Ajoutez une affectation numérique" in out


def test_diagnose_sandbox_reports_forbidden_import(
    monkeypatch, tmp_path, capsys
) -> None:
    home = tmp_path / "life"
    _write_skill(home, "import_os.py", "import os\nresult = 1\n")

    exit_code = cli.main(["--home", str(home), "diagnose", "sandbox"])

    out = capsys.readouterr().out
    assert exit_code == 1
    assert "import_os.py | KO | - | sandbox_error" in out
    assert "forbidden syntax detected" in out
    assert "Supprimez les imports/with" in out


def test_diagnose_sandbox_reports_non_numeric_result(
    monkeypatch, tmp_path, capsys
) -> None:
    home = tmp_path / "life"
    _write_skill(home, "text.py", 'result = "texte"\n')

    exit_code = cli.main(["--home", str(home), "diagnose", "sandbox"])

    out = capsys.readouterr().out
    assert exit_code == 1
    assert "text.py | KO | - | non_numeric_result" in out
    assert "Convertissez `result` en nombre" in out


def test_diagnose_sandbox_reports_timeout(monkeypatch, tmp_path, capsys) -> None:
    home = tmp_path / "life"
    _write_skill(home, "timeout.py", "while True:\n    pass\n")

    exit_code = cli.main(["--home", str(home), "diagnose", "sandbox"])

    out = capsys.readouterr().out
    assert exit_code == 1
    assert "timeout.py | KO | - | timeout" in out
    assert "Réduisez les boucles" in out
