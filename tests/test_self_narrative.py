from datetime import datetime, timedelta, timezone
from pathlib import Path

from singular.self_narrative import (
    SCHEMA_VERSION,
    load,
    summarize_long,
    summarize_short,
    update_from_signals,
)


def test_load_creates_default_file_when_missing(tmp_path: Path) -> None:
    path = tmp_path / "mem" / "self_narrative.json"

    narrative = load(path)

    assert path.exists()
    assert narrative.schema_version == SCHEMA_VERSION
    assert narrative.identity.name == "Singular"
    assert set(narrative.trait_trends) == {
        "curiosity",
        "patience",
        "playfulness",
        "optimism",
        "resilience",
    }


def test_load_fallback_on_corrupted_file(tmp_path: Path) -> None:
    path = tmp_path / "mem" / "self_narrative.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not-valid-json", encoding="utf-8")

    narrative = load(path)

    assert narrative.identity.name == "Singular"
    backups = list(path.parent.glob("self_narrative.json.corrupt-*"))
    assert backups


def test_update_from_signals_persists_expected_shape(tmp_path: Path) -> None:
    path = tmp_path / "mem" / "self_narrative.json"
    born_at = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()

    narrative = update_from_signals(
        {
            "identity": {"name": "Nova", "born_at": born_at},
            "current_heading": "Construire une mémoire plus robuste.",
            "life_periods": [
                {
                    "title": "Redémarrage",
                    "start_at": "2026-04-10T00:00:00+00:00",
                    "highlights": ["nettoyage", "recentrage"],
                }
            ],
            "trait_trends": {
                "curiosity": {"value": 0.8, "trend": "up"},
                "patience": {"value": 0.55, "trend": "stable"},
            },
            "regrets_and_pride": {
                "significant_successes": ["stabilité retrouvée"],
                "significant_failures": ["boucle trop coûteuse"],
                "abandoned_skills": ["heuristique-v0"],
                "costly_incidents": ["fuite mémoire"],
            },
        },
        path=path,
    )

    assert narrative.identity.name == "Nova"
    assert narrative.identity.logical_age >= 5
    assert narrative.life_periods[-1].title == "Redémarrage"
    assert narrative.trait_trends["curiosity"].trend == "up"
    assert "stabilité retrouvée" in narrative.regrets_and_pride.significant_successes


def test_summaries_include_current_heading(tmp_path: Path) -> None:
    path = tmp_path / "mem" / "self_narrative.json"
    update_from_signals({"current_heading": "Mieux décider."}, path)

    short = summarize_short(path=path)
    long = summarize_long(path=path)

    assert "cap" in short
    assert "Mieux décider." in short
    assert "Cap actuel" in long
    assert "Mieux décider." in long
