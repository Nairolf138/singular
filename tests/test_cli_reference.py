"""Static parity checks between argparse and the bilingual CLI reference."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from singular.cli import _build_parser

COMMAND_MARKER = re.compile(r"^<!-- cli-command: (.+) -->$", re.MULTILINE)
REFERENCE_FILES = (
    Path("docs/cli-reference.fr.md"),
    Path("docs/cli-reference.en.md"),
)


def _argparse_command_paths(
    parser: argparse.ArgumentParser, prefix: tuple[str, ...] = ()
) -> set[str]:
    """Return canonical command paths, ignoring aliases of the same parser."""

    paths: set[str] = set()
    for action in parser._actions:
        if not isinstance(action, argparse._SubParsersAction):
            continue
        seen_parsers: set[int] = set()
        for name, child in action.choices.items():
            if id(child) in seen_parsers:
                continue
            seen_parsers.add(id(child))
            child_prefix = (*prefix, name)
            paths.add(" ".join(child_prefix))
            paths.update(_argparse_command_paths(child, child_prefix))
    return paths


def test_every_argparse_command_is_documented_in_both_languages(
    monkeypatch,
) -> None:
    """Fail when a parser is added without matching FR and EN sections."""

    monkeypatch.setenv("SINGULAR_ENABLE_BIRTH_ALIAS", "1")
    expected = _argparse_command_paths(_build_parser())

    for reference in REFERENCE_FILES:
        contents = reference.read_text(encoding="utf-8")
        markers = COMMAND_MARKER.findall(contents)
        assert len(markers) == len(set(markers)), f"duplicate marker in {reference}"
        assert set(markers) == expected, (
            f"{reference} is out of sync with _build_parser: "
            f"missing={sorted(expected - set(markers))}, "
            f"extra={sorted(set(markers) - expected)}"
        )


def test_each_reference_entry_covers_the_documentation_contract() -> None:
    """Keep each command entry useful, not merely present as an empty heading."""

    required_fr = (
        "**Syntaxe :**",
        "**Arguments et défauts :**",
        "**Prérequis :**",
        "**Root et vie ciblés :**",
        "**Fichiers lus ou écrits :**",
        "**Effets de bord :**",
        "**Exemple minimal :**",
        "**Exemple avancé :**",
        "**Erreurs usuelles :**",
    )
    required_en = (
        "**Syntax :**",
        "**Arguments and defaults :**",
        "**Prerequisites :**",
        "**Target root and life :**",
        "**Files read or written :**",
        "**Side effects :**",
        "**Minimal example :**",
        "**Advanced example :**",
        "**Common errors :**",
    )

    for reference, required in zip(REFERENCE_FILES, (required_fr, required_en)):
        contents = reference.read_text(encoding="utf-8")
        entries = COMMAND_MARKER.split(contents)[2::2]
        for entry in entries:
            for label in required:
                assert label in entry, f"{label} missing from an entry in {reference}"
