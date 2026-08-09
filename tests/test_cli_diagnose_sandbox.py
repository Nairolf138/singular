from __future__ import annotations

from pathlib import Path

import singular.cli as cli


def test_autonomous_generation_is_explicitly_optional(monkeypatch, tmp_path) -> None:
    from singular.diagnostics import autonomous

    monkeypatch.setenv("SINGULAR_ROOT", str(tmp_path))
    report = autonomous.autonomous_diagnostics(run_generation=False)
    generation = next(
        c for c in report["checks"] if c["check_id"] == "minimal_generation"
    )
    assert generation["state"] == "ready"
    assert generation["evidence"]["requested"] is False


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
    assert "import_os.py | KO | - | forbidden_syntax" in out
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


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json_line(row) for row in rows), encoding="utf-8")


def json_line(row: dict[str, object]) -> str:
    import json

    return json.dumps(row) + "\n"


def test_diagnose_evolution_reports_table_patterns(tmp_path, capsys) -> None:
    home = tmp_path / "life"
    _write_jsonl(
        home / "runs" / "run-1" / "events.jsonl",
        [
            {"event": "skill.timeout", "error_type": "timeout"},
            {"event": "skill.timeout", "message": "timeout"},
            {"event": "skill.scored", "score": "-inf"},
            {
                "event_type": "governance.circuit_breaker_opened",
                "payload": {"category": "sandbox_violation"},
            },
            {"event_type": "skill.quarantined", "payload": {"skill": "a"}},
        ],
    )
    _write_jsonl(
        home / "mem" / "episodic.jsonl",
        [
            {"event": "skill.quarantined", "skill": "b"},
            {"event": "autogen.validation_failed", "reason": "invalid syntax"},
        ],
    )

    exit_code = cli.main(["--home", str(home), "diagnose", "evolution"])

    out = capsys.readouterr().out
    assert exit_code == 1
    assert "Diagnostic évolution:" in out
    assert "timeout_rate | KO | 2 | 2/7" in out
    assert "negative_infinite_scores | KO | 1" in out
    assert "breaker_open | KO | 1" in out
    assert "repeated_quarantine | KO | 2" in out
    assert "invalid_autogen | KO | 1" in out
    assert "recommandation" in out


def test_diagnose_evolution_json_ok_when_no_patterns(tmp_path, capsys) -> None:
    home = tmp_path / "life"
    _write_jsonl(
        home / "runs" / "run-1" / "events.jsonl", [{"event": "tick.ok", "score": 1.0}]
    )

    exit_code = cli.main(
        ["--home", str(home), "--format", "json", "diagnose", "evolution"]
    )

    import json

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["events_analyzed"] == 1
    assert all(not row["detected"] for row in payload["patterns"])


def test_diagnose_evolution_does_not_treat_candidate_incident_as_global_breaker(
    tmp_path, capsys
) -> None:
    home = tmp_path / "life"
    _write_jsonl(
        home / "runs" / "run-1" / "events.jsonl",
        [
            {
                "event": "sandbox_violation",
                "category": "invalid_mutation",
                "scope": "candidate",
            }
        ],
    )

    cli.main(["--home", str(home), "diagnose", "evolution"])

    assert "breaker_open | OK | 0" in capsys.readouterr().out
