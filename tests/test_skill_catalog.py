from pathlib import Path
import hashlib
import json

from singular.life.skill_catalog import read_skill_catalog, refresh_skill_catalog


def test_refresh_skill_catalog_extracts_docstring_annotations(tmp_path: Path) -> None:
    skills_dir = tmp_path / "skills"
    mem_dir = tmp_path / "mem"
    skills_dir.mkdir(parents=True)
    mem_dir.mkdir(parents=True)

    (skills_dir / "math_skill.py").write_text(
        '"""Capabilities: math, arithmetic\n'
        "Preconditions: numeric_input\n"
        "Input: dict[str, float]\n"
        "Output: float\n"
        "Cost: 0.2\n"
        "Reliability: 0.9\n"
        '"""\n\n'
        "def run(context: dict[str, float]) -> float:\n"
        "    return float(context.get('x', 0.0))\n",
        encoding="utf-8",
    )

    catalog = refresh_skill_catalog(skills_dir=skills_dir, mem_dir=mem_dir)

    assert "math_skill" in catalog
    descriptor = catalog["math_skill"]
    assert descriptor["capability_tags"] == ["math", "arithmetic"]
    assert descriptor["preconditions"] == ["numeric_input"]
    assert descriptor["input_format"] == "dict[str, float]"
    assert descriptor["output_format"] == "float"
    assert descriptor["estimated_cost"] == 0.2
    assert descriptor["reliability"] == 0.9
    assert descriptor["annotation_valid"] is True

    reloaded = read_skill_catalog(mem_dir)
    assert reloaded["math_skill"]["capability_tags"] == ["math", "arithmetic"]


def test_catalog_marks_mutated_validated_skill_as_regressed(tmp_path: Path) -> None:
    skills_dir = tmp_path / "skills"
    mem_dir = tmp_path / "mem"
    skills_dir.mkdir()
    mem_dir.mkdir()
    original = "def run(context=None):\n    return {'ok': True}\n"
    path = skills_dir / "generated.py"
    path.write_text(original)
    (mem_dir / "skills.json").write_text(
        json.dumps(
            {
                "generated": {
                    "publication_state": "available",
                    "source_sha256": hashlib.sha256(original.encode()).hexdigest(),
                }
            }
        )
    )
    path.write_text("def run(context=None):\n    return {'ok': False}\n")

    descriptor = refresh_skill_catalog(skills_dir=skills_dir, mem_dir=mem_dir)[
        "generated"
    ]

    assert descriptor["publication_state"] == "regressed"
    assert descriptor["implementation_valid"] is False
