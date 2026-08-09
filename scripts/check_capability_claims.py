#!/usr/bin/env python3
"""Reject unvalidated completeness claims about cognitive capabilities in docs."""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
CAPABILITY = re.compile(
    r"rag autobiographique|m[ée]tacognition|th[ée]orie de l'esprit|morale|"
    r"narration|ros2|incarnation|imitation|apprentissage continu|d[ée]veloppement|sommeil",
    re.IGNORECASE,
)
COMPLETENESS = re.compile(
    r"capacit[ée].{0,50}(?:compl[èe]te|achev[ée]e|production[- ]ready)|"
    r"(?:compl[èe]te|achev[ée]e|production[- ]ready).{0,50}capacit[ée]",
    re.IGNORECASE,
)
VALIDATED_ROW = re.compile(
    r"^\|\s*(?P<name>[^|]+?)\s*\|\s*`validé`\s*\|"
    r"\s*oui\s*/\s*oui\s*/\s*oui\s*/\s*oui\s*\|",
    re.MULTILINE | re.IGNORECASE,
)


def _has_campaign(name: str, errors: list[str]) -> bool:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.casefold()).strip("-")
    path = ROOT / "artifacts" / "agi_kpis" / f"{slug}.json"
    if not path.is_file():
        errors.append(f"{path.relative_to(ROOT)}: missing validation campaign")
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        windows = payload["windows"]
        valid = (
            payload.get("acceptance_scenario_passed") is True
            and len(windows) >= 2
            and all(item["sample_count"] >= 200 for item in windows[-2:])
            and all(item["confidence_level"] >= 0.95 for item in windows[-2:])
            and all(
                {"domain", "language", "task_difficulty"} <= set(item["segments"])
                for item in windows[-2:]
            )
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"{path.relative_to(ROOT)}: invalid campaign: {exc}")
        return False
    if not valid:
        errors.append(
            f"{path.relative_to(ROOT)}: campaign does not meet validation gates"
        )
    return valid


def main() -> int:
    matrix = (DOCS / "cognitive-capabilities-matrix.md").read_text(encoding="utf-8")
    errors: list[str] = []
    validated = {
        match.group("name").strip(" *").casefold()
        for match in VALIDATED_ROW.finditer(matrix)
        if _has_campaign(match.group("name").strip(" *"), errors)
    }
    for path in sorted(DOCS.rglob("*.md")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not COMPLETENESS.search(line):
                continue
            named = {match.group(0).casefold() for match in CAPABILITY.finditer(line)}
            if named and not named <= validated:
                errors.append(f"{path.relative_to(ROOT)}:{number}: {line.strip()}")
    if errors:
        print("Claims of completeness require a `validé` matrix row:")
        print("\n".join(errors))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
