"""Birth command implementation."""

from __future__ import annotations

import os
import random
import string
import json
from math import isfinite
from pathlib import Path
from typing import Any

from ..governance.values import ValueWeights
from ..identity import create_identity
from ..memory import ensure_memory_structure, update_score, write_profile
from ..psyche import Psyche
from ..life.skill_catalog import refresh_skill_catalog


_PSYCHE_TRAITS = ("curiosity", "patience", "playfulness", "optimism", "resilience")
_PSYCHE_DEFAULTS = {trait: 0.5 for trait in _PSYCHE_TRAITS}
_DEFAULT_STARTER_PROFILE = "minimal"
_STARTER_CONFIG_PATH = Path(__file__).resolve().parents[3] / "configs" / "starter_skills.yaml"
_DEFAULT_STARTER_PROFILES: dict[str, list[str]] = {
    "minimal": ["addition", "subtraction", "multiplication"],
}
_SKILL_TEMPLATES: dict[str, str] = {
    "addition": (
        '"""Simple addition skill."""\n\n'
        "def add(a: float, b: float) -> float:\n"
        '    """Return the sum of ``a`` and ``b``."""\n'
        "    return a + b\n"
    ),
    "subtraction": (
        '"""Simple subtraction skill."""\n\n'
        "def subtract(a: float, b: float) -> float:\n"
        '    """Return the difference of ``a`` and ``b``."""\n'
        "    return a - b\n"
    ),
    "multiplication": (
        '"""Simple multiplication skill."""\n\n'
        "def multiply(a: float, b: float) -> float:\n"
        '    """Return the product of ``a`` and ``b``."""\n'
        "    return a * b\n"
    ),
    "validation": (
        '"""Validation helpers for basic input checks."""\n\n'
        "def validate_non_empty_text(text: str) -> bool:\n"
        '    """Return ``True`` when ``text`` contains non-whitespace characters."""\n'
        "    return bool(text.strip())\n"
    ),
    "summary": (
        '"""Summary helpers for short text snippets."""\n\n'
        "def summarize_preview(text: str, max_words: int = 12) -> str:\n"
        '    """Return the first ``max_words`` words from ``text`` for quick previews."""\n'
        "    words = text.split()\n"
        "    return \" \".join(words[:max_words])\n"
    ),
    "intent_classification": (
        '"""Intent classification helper using simple keyword heuristics."""\n\n'
        "def classify_intent(message: str) -> str:\n"
        '    """Return ``question``, ``request`` or ``statement`` from ``message``."""\n'
        "    lowered = message.strip().lower()\n"
        "    if not lowered:\n"
        '        return "statement"\n'
        "    if lowered.endswith(\"?\"):\n"
        '        return "question"\n'
        "    request_markers = (\"please\", \"peux-tu\", \"merci de\", \"fais\")\n"
        "    if any(marker in lowered for marker in request_markers):\n"
        '        return "request"\n'
        '    return "statement"\n'
    ),
    "entity_extraction": (
        '"""Entity extraction helper for lightweight token detection."""\n\n'
        "def extract_capitalized_entities(text: str) -> list[str]:\n"
        '    """Return unique capitalized tokens found in ``text`` preserving order."""\n'
        "    entities: list[str] = []\n"
        "    seen: set[str] = set()\n"
        "    for token in text.split():\n"
        "        cleaned = token.strip(\".,;:!?()[]{}\\\"'\")\n"
        "        if cleaned and cleaned[0].isupper() and cleaned not in seen:\n"
        "            entities.append(cleaned)\n"
        "            seen.add(cleaned)\n"
        "    return entities\n"
    ),
    "planning": (
        '"""Planning helper to build a simple ordered checklist."""\n\n'
        "def build_plan(goal: str, steps: list[str]) -> dict[str, object]:\n"
        '    """Return a normalized plan payload for ``goal`` and ordered ``steps``."""\n'
        "    cleaned_steps = [step.strip() for step in steps if step.strip()]\n"
        "    return {\n"
        '        "goal": goal.strip(),\n'
        '        "steps": cleaned_steps,\n'
        '        "total_steps": len(cleaned_steps),\n'
        "    }\n"
    ),
    "metrics": (
        '"""Metrics helper to compute simple completion ratios."""\n\n'
        "def completion_ratio(completed: int, total: int) -> float:\n"
        '    """Return a bounded completion ratio in ``[0.0, 1.0]``."""\n'
        "    if total <= 0:\n"
        "        return 0.0\n"
        "    ratio = completed / total\n"
        "    return max(0.0, min(1.0, ratio))\n"
    ),
}


def _resolve_psyche_overrides(
    overrides: dict[str, Any] | None,
) -> dict[str, float]:
    """Validate and normalize optional psyche trait overrides."""

    if not overrides:
        return {}

    normalized: dict[str, float] = {}
    for key, raw_value in overrides.items():
        if key not in _PSYCHE_DEFAULTS:
            raise ValueError(f"unsupported psyche trait override: {key}")
        try:
            value = float(raw_value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid psyche trait override for {key}: {raw_value!r}") from exc
        if not isfinite(value) or value < 0.0 or value > 1.0:
            raise ValueError(f"psyche trait override out of range for {key}: {value!r}")
        normalized[key] = value
    return normalized


def _load_starter_profiles(config_path: Path = _STARTER_CONFIG_PATH) -> dict[str, list[str]]:
    """Load starter skill profiles from configuration with a safe default fallback."""

    if not config_path.exists():
        return dict(_DEFAULT_STARTER_PROFILES)

    raw = config_path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore
    except ImportError:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return dict(_DEFAULT_STARTER_PROFILES)
    else:
        data = yaml.safe_load(raw)

    if not isinstance(data, dict):
        return dict(_DEFAULT_STARTER_PROFILES)
    profiles = data.get("profiles")
    if not isinstance(profiles, dict):
        return dict(_DEFAULT_STARTER_PROFILES)

    normalized: dict[str, list[str]] = {}
    for profile, skills in profiles.items():
        if isinstance(profile, str) and isinstance(skills, list):
            normalized[profile] = [skill for skill in skills if isinstance(skill, str)]
    if _DEFAULT_STARTER_PROFILE not in normalized:
        normalized[_DEFAULT_STARTER_PROFILE] = list(
            _DEFAULT_STARTER_PROFILES[_DEFAULT_STARTER_PROFILE]
        )
    return normalized


def _resolve_starter_skills(
    profile: str | None,
    extra_skills: list[str] | None,
    *,
    profiles: dict[str, list[str]] | None = None,
) -> list[str]:
    """Resolve starter skill identifiers from profile and optional explicit extras."""

    available_profiles = profiles or _load_starter_profiles()
    selected_profile = profile or _DEFAULT_STARTER_PROFILE
    base_skills = available_profiles.get(selected_profile)
    if base_skills is None:
        base_skills = available_profiles.get(
            _DEFAULT_STARTER_PROFILE,
            _DEFAULT_STARTER_PROFILES[_DEFAULT_STARTER_PROFILE],
        )

    ordered: list[str] = []
    seen: set[str] = set()
    for skill_id in [*base_skills, *(extra_skills or [])]:
        if skill_id in _SKILL_TEMPLATES and skill_id not in seen:
            ordered.append(skill_id)
            seen.add(skill_id)
    return ordered


def birth(
    seed: int | None = None,
    home: Path | None = None,
    *,
    psyche_overrides: dict[str, Any] | None = None,
    starter_profile: str = _DEFAULT_STARTER_PROFILE,
    starter_skills: list[str] | None = None,
) -> None:
    """Handle the ``birth`` subcommand.

    Parameters
    ----------
    seed:
        Optional random seed for reproducibility.
    """
    if home is None:
        if "SINGULAR_HOME" in os.environ:
            home = Path(os.environ["SINGULAR_HOME"])
        else:
            home = Path.cwd()
    else:
        home = Path(home)

    home.mkdir(parents=True, exist_ok=True)
    ensure_memory_structure(home / "mem")
    values_path = home / "mem" / "values.yaml"
    if values_path.stat().st_size == 0:
        defaults = ValueWeights().to_dict()
        values_path.write_text(
            (
                "values:\n"
                f"  securite: {defaults['securite']}\n"
                f"  utilite_utilisateur: {defaults['utilite_utilisateur']}\n"
                f"  preservation_memoire: {defaults['preservation_memoire']}\n"
                f"  curiosite_bornee: {defaults['curiosite_bornee']}\n"
            ),
            encoding="utf-8",
        )

    skills_dir = home / "skills"
    if not skills_dir.exists() or not any(skills_dir.iterdir()):
        skills_dir.mkdir(parents=True, exist_ok=True)
        selected_skills = _resolve_starter_skills(starter_profile, starter_skills)
        for skill_id in selected_skills:
            (skills_dir / f"{skill_id}.py").write_text(
                _SKILL_TEMPLATES[skill_id], encoding="utf-8"
            )
            update_score(
                skill_id,
                0.0,
                path=home / "mem" / "skills.json",
            )

    refresh_skill_catalog(skills_dir=skills_dir, mem_dir=home / "mem")

    if seed is not None:
        random.seed(seed)

    # Generate a random name and soulseed for the new identity
    name = f"organism-{random.randint(0, 999999):06d}"
    soulseed = "".join(random.choices(string.ascii_lowercase + string.digits, k=16))

    # Create the identity file and persist a base profile
    identity = create_identity(name, soulseed, path=home / "id.json")
    write_profile(identity.__dict__, path=home / "mem" / "profile.json")

    resolved_overrides = _resolve_psyche_overrides(psyche_overrides)
    initial_traits = {**_PSYCHE_DEFAULTS, **resolved_overrides}

    # Initialize the psyche with validated traits and save its state
    psyche = Psyche(**initial_traits)
    psyche.save_state(path=home / "mem" / "psyche.json")
