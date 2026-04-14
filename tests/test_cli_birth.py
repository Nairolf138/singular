from __future__ import annotations

import json
from pathlib import Path

import pytest

from singular.cli import main
from singular.lives import load_registry


def test_birth_persists_initial_psyche_overrides(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "registry-root"
    monkeypatch.delenv("SINGULAR_ROOT", raising=False)
    monkeypatch.delenv("SINGULAR_HOME", raising=False)

    main(
        [
            "--root",
            str(root),
            "birth",
            "--name",
            "Prudent",
            "--curiosity",
            "0.2",
            "--patience",
            "0.9",
            "--playfulness",
            "0.1",
            "--optimism",
            "0.55",
            "--resilience",
            "0.95",
        ]
    )

    registry = load_registry()
    slug = registry["active"]
    assert isinstance(slug, str)
    meta = registry["lives"][slug]

    psyche_path = Path(meta.path) / "mem" / "psyche.json"
    payload = json.loads(psyche_path.read_text(encoding="utf-8"))

    assert payload["curiosity"] == 0.2
    assert payload["patience"] == 0.9
    assert payload["playfulness"] == 0.1
    assert payload["optimism"] == 0.55
    assert payload["resilience"] == 0.95


def test_birth_rejects_out_of_range_psyche_override() -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["birth", "--curiosity", "1.5"])
    assert excinfo.value.code == 2
