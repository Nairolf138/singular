from __future__ import annotations

import json

import pytest

import singular.cli as cli
from singular.beliefs.store import BeliefStore
from singular.governance.policy import load_runtime_policy
from singular.lives import load_registry


def test_life_relationships_archive_memorial_and_clone(
    tmp_path, monkeypatch, capsys
) -> None:
    root = tmp_path / "root"
    monkeypatch.delenv("SINGULAR_HOME", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))

    def command(*args: str) -> int:
        return cli.main(["--root", str(root), *args])

    assert command("lives", "create", "--name", "Alpha") == 0
    assert command("lives", "create", "--name", "Beta") == 0
    registry = load_registry()
    alpha, beta = sorted(registry["lives"])
    capsys.readouterr()

    assert command("lives", "ally", alpha, beta) == 0
    capsys.readouterr()
    assert command("--format", "json", "lives", "relations", "--name", alpha) == 0
    assert beta in json.loads(capsys.readouterr().out)["focus"]["allies"]
    assert command("lives", "rival", alpha, beta) == 0
    assert command("lives", "reconcile", alpha, beta) == 0
    assert command("lives", "proximity", alpha, "--score", "0.7") == 0
    assert "0.70" in capsys.readouterr().out
    assert command("--format", "json", "lives", "relations", "--name", alpha) == 0
    focus = json.loads(capsys.readouterr().out)["focus"]
    assert focus["proximity_score"] == 0.7
    assert beta not in focus["rivals"]
    assert command("lives", "relations", "--name", alpha) == 0
    assert "Score proximité: 0.70" in capsys.readouterr().out

    assert command("--format", "json", "lives", "reproduce", alpha, beta) == 0
    reproduction = json.loads(capsys.readouterr().out)
    assert reproduction["status"] in {"suspended", "created"}

    assert command("lives", "archive", alpha) == 0
    assert "Vie archivée" in capsys.readouterr().out
    assert command("lives", "memorial", alpha, "--message", "Merci Alpha") == 0
    assert "Mémorial enregistré" in capsys.readouterr().out
    assert command("lives", "clone", alpha, "--new-name", "Gamma") == 0
    assert "Vie clonée" in capsys.readouterr().out
    assert len(load_registry()["lives"]) == 3
    assert command("lives", "delete", beta) == 0
    assert "Vie supprimée" in capsys.readouterr().out
    assert len(load_registry()["lives"]) == 2


def test_values_policy_and_belief_formats(tmp_path, monkeypatch, capsys) -> None:
    root = tmp_path / "root"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    assert cli.main(["--root", str(root), "lives", "create", "--name", "Alpha"]) == 0
    capsys.readouterr()

    assert cli.main(["--root", str(root), "--format", "json", "values", "show"]) == 0
    assert json.loads(capsys.readouterr().out)["values"]
    assert cli.main(["--root", str(root), "--format", "table", "values", "show"]) == 0
    assert "Poids" in capsys.readouterr().out
    assert cli.main(["--root", str(root), "values", "show"]) == 0
    assert "Valeurs critiques" in capsys.readouterr().out

    assert cli.main(["--root", str(root), "--format", "json", "policy", "show"]) == 0
    assert json.loads(capsys.readouterr().out)["policy"]["impact"]
    assert cli.main(["--root", str(root), "--format", "table", "policy", "show"]) == 0
    assert "Impact:" in capsys.readouterr().out
    assert cli.main(["--root", str(root), "policy", "show"]) == 0
    assert "Impact:" in capsys.readouterr().out
    assert (
        cli.main(
            [
                "--root",
                str(root),
                "policy",
                "set",
                "--key",
                "autonomy.safe_mode",
                "--value",
                "not-a-bool",
            ]
        )
        == 1
    )
    assert "Valeur invalide" in capsys.readouterr().err
    assert (
        cli.main(
            [
                "--root",
                str(root),
                "policy",
                "set",
                "--key",
                "autonomy.safe_mode",
                "--value",
                "true",
            ]
        )
        == 0
    )
    assert "Politique mise à jour" in capsys.readouterr().out
    assert load_runtime_policy(root / "policy.yaml").safe_mode is True

    life = next(iter(load_registry()["lives"].values())).path
    store = BeliefStore(path=life / "mem" / "beliefs.json")
    store.update_after_run("operator:demo", success=True, evidence="accepted")
    for format_name in ("json", "table", "plain"):
        assert (
            cli.main(["--home", str(life), "--format", format_name, "beliefs", "audit"])
            == 0
        )
        assert "operator:demo" in capsys.readouterr().out
    assert (
        cli.main(["--home", str(life), "beliefs", "reset", "--prefix", "operator:"])
        == 0
    )
    assert "supprimées" in capsys.readouterr().out
    assert BeliefStore(path=life / "mem" / "beliefs.json").list_beliefs() == []
    assert cli.main(["--home", str(life), "beliefs", "audit"]) == 0
    assert "Aucune croyance" in capsys.readouterr().out
    store.update_after_run("new-hypothesis", success=False, evidence="rejected")
    assert cli.main(["--home", str(life), "beliefs", "reset", "--all"]) == 0
    assert "(all):" in capsys.readouterr().out


def test_unknown_life_is_reported_without_mutating_registry(tmp_path, capsys) -> None:
    root = tmp_path / "root"
    assert cli.main(["--root", str(root), "lives", "list"]) == 0
    assert "Aucune vie enregistrée" in capsys.readouterr().out
    with pytest.raises(SystemExit, match="Vie introuvable"):
        cli.main(["--root", str(root), "lives", "archive", "missing"])
    with pytest.raises(SystemExit, match="Vie introuvable"):
        cli.main(["--root", str(root), "lives", "relations", "--name", "missing"])
    with pytest.raises(SystemExit, match="Vie introuvable"):
        cli.main(["--root", str(root), "lives", "delete", "missing"])
    assert "Aucune vie" not in capsys.readouterr().out


def test_quickstart_prompt_creates_a_named_life(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "_can_prompt", lambda: True)
    monkeypatch.setattr(cli, "_prompt_text", lambda *_args: "Vega")
    monkeypatch.setattr(cli, "_prompt_yes_no", lambda *_args, **_kwargs: False)

    assert cli.main(["--root", str(tmp_path / "universe"), "quickstart"]) == 0
    assert "Vie créée: Vega" in capsys.readouterr().out
    assert load_registry()["active"] == "vega"


def test_invalid_policy_file_reports_validation_error(tmp_path, capsys) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "policy.yaml").write_text("invalid: true\n", encoding="utf-8")

    assert cli.main(["--root", str(root), "policy", "show"]) == 1
    assert "Erreur de validation policy.yaml" in capsys.readouterr().err


def test_policy_value_parser_rejects_ambiguous_lists_and_types() -> None:
    assert cli._parse_policy_value("bool", "non") is False
    assert cli._parse_policy_value("int", "4") == 4
    assert cli._parse_policy_value("float", "0.25") == 0.25
    assert cli._parse_policy_value("paths", " /skills/, /mem/ ") == ("skills", "mem")
    assert cli._parse_policy_value("strings", "alpha, beta") == ("alpha", "beta")
    assert cli._parse_policy_value("paths", "") == ()
    assert cli._parse_policy_value("strings", "") == ()
    for kind, raw in (("paths", "skills,,mem"), ("strings", "a,,b"), ("unknown", "a")):
        with pytest.raises(ValueError):
            cli._parse_policy_value(kind, raw)


def test_ecosystem_and_life_inspection_commands_target_selected_root(
    tmp_path, monkeypatch, capsys
) -> None:
    monkeypatch.chdir(tmp_path)
    root = tmp_path / "root"
    for name in ("Alpha", "Beta"):
        assert cli.main(["--root", str(root), "lives", "create", "--name", name]) == 0
    capsys.readouterr()
    invocations = []
    monkeypatch.setattr(
        "singular.runs.loop.loop", lambda **kwargs: invocations.append(kwargs)
    )

    assert (
        cli.main(
            [
                "--root",
                str(root),
                "ecosystem",
                "run",
                "--life-group",
                "alpha,beta",
                "--budget-seconds",
                "0.1",
            ]
        )
        == 0
    )
    assert set(invocations[-1]["skills_dirs"]) == {"alpha", "beta"}
    assert all(
        path.is_relative_to(root) for path in invocations[-1]["skills_dirs"].values()
    )

    assert cli.main(["--root", str(root), "--format", "json", "lives", "list"]) == 0
    assert len(json.loads(capsys.readouterr().out)["lives"]) == 2
    assert cli.main(["--root", str(root), "--format", "table", "lives", "list"]) == 0
    assert "Alpha" in capsys.readouterr().out
    assert cli.main(["--root", str(root), "skills", "list"]) == 0
    capsys.readouterr()
    assert cli.main(["--root", str(root), "--format", "json", "skills", "list"]) == 0
    assert isinstance(json.loads(capsys.readouterr().out), dict)
    assert cli.main(["--root", str(root), "quest", "create", "--schema"]) == 0
    assert "required" in json.loads(capsys.readouterr().out)
    assert cli.main(["--root", str(root), "--format", "json", "quest", "list"]) == 0
    assert json.loads(capsys.readouterr().out) == []
    assert cli.main(["--root", str(root), "report"]) == 1
    assert "No run log" in capsys.readouterr().out
    assert cli.main(["--root", str(root), "social", "interact", "alpha", "helped"]) == 0
    assert json.loads(capsys.readouterr().out)["mental_state"]
    assert cli.main(["--root", str(root), "cognition", "self-observe"]) == 0
    assert isinstance(json.loads(capsys.readouterr().out), dict)
    assert cli.main(["--root", str(root), "self-narrative", "summarize"]) == 0
    assert capsys.readouterr().out.strip()

    from singular.runs import report as report_module

    reports = []
    monkeypatch.setattr(
        report_module, "report", lambda **kwargs: reports.append(kwargs)
    )
    assert cli.main(["--root", str(root), "report", "--id", "known-run"]) == 0
    assert reports[-1]["run_id"] == "known-run"

    from singular.organisms import status as status_module

    statuses = []
    monkeypatch.setattr(
        status_module, "status", lambda **kwargs: statuses.append(kwargs)
    )
    assert cli.main(["--root", str(root), "monitor"]) == 0
    assert statuses[-1]["output_format"] == "plain"

    with pytest.raises(SystemExit, match="Aucune vie fournie"):
        cli.main(["--root", str(root), "ecosystem", "run", "--budget-seconds", "0.1"])
    with pytest.raises(SystemExit, match="Vie introuvable"):
        cli.main(
            [
                "--root",
                str(root),
                "ecosystem",
                "run",
                "--life",
                "missing",
                "--budget-seconds",
                "0.1",
            ]
        )
