from __future__ import annotations

import ast
import json
from pathlib import Path

import singular.cli as cli
from singular.life import loop as life_loop
from singular.lives import bootstrap_life
from singular.runs.generations import get_generations_path, record_generation


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_generation_registry_stays_coherent_with_run_events(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SINGULAR_HOME", str(tmp_path))
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)
    (skills_dir / "addition.py").write_text(
        "def run(x:int,y:int)->int:\n    return x+y\n",
        encoding="utf-8",
    )

    def noop_operator(tree: ast.AST, rng=None) -> ast.AST:
        return tree

    checkpoint = tmp_path / "life_checkpoint.json"
    life_loop.run(
        skills_dirs=skills_dir,
        checkpoint_path=checkpoint,
        budget_seconds=0.2,
        run_id="gen-coherence",
        operators={"noop": noop_operator},
        max_iterations=1,
    )

    generations = _read_jsonl(get_generations_path(tmp_path))
    assert len(generations) == 1
    generation = generations[0]
    assert generation["run_id"] == "gen-coherence"

    candidate_paths = list(Path.cwd().glob("runs/gen-coherence/events.jsonl"))
    candidate_paths += list(tmp_path.glob("runs/gen-coherence/events.jsonl"))
    assert candidate_paths
    events_path = max(candidate_paths, key=lambda p: p.stat().st_mtime)
    events = _read_jsonl(events_path)
    mutation_events = [entry for entry in events if entry.get("event_type") == "mutation"]
    assert mutation_events
    mutation_payload = mutation_events[-1]["payload"]

    assert generation["mutation"]["operator"] == mutation_payload["op"]
    assert generation["score"]["base"] == mutation_payload["score_base"]
    assert generation["score"]["new"] == mutation_payload["score_new"]


def test_cli_rollback_generation_restores_stable_snapshot(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SINGULAR_ROOT", str(tmp_path))
    metadata = bootstrap_life("Rollback Life")
    monkeypatch.setenv("SINGULAR_HOME", str(metadata.path))

    skill_path = metadata.path / "skills" / "sample.py"
    skill_path.parent.mkdir(parents=True, exist_ok=True)
    skill_path.write_text("def f():\n    return 1\n", encoding="utf-8")

    generation = record_generation(
        run_id="rollback-run",
        iteration=1,
        skill="sample",
        operator="noop",
        mutation_diff="",
        score_base=1.0,
        score_new=1.0,
        accepted=True,
        reason="accepted: stable",
        parent_hash="basehash",
        candidate_code="def f():\n    return 2\n",
        skill_relative_path="skills/sample.py",
        security_metadata={"governance_checked": True, "allowed": True},
        base_dir=metadata.path,
    )

    skill_path.write_text("def f():\n    return 999\n", encoding="utf-8")

    exit_code = cli.main([
        "--root",
        str(tmp_path),
        "--life",
        metadata.slug,
        "rollback",
        "--generation",
        str(generation["generation_id"]),
    ])

    assert exit_code == 0
    assert "return 2" in skill_path.read_text(encoding="utf-8")
