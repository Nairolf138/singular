"""Synchronize dashboard branding copies from their canonical assets."""

from __future__ import annotations

import shutil
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CANONICAL_BRANDING = REPOSITORY_ROOT / "docs" / "assets" / "branding"
DASHBOARD_STATIC = REPOSITORY_ROOT / "src" / "singular" / "dashboard" / "static"

BRANDING_COPIES = {
    CANONICAL_BRANDING
    / "singular-icon.svg": (
        DASHBOARD_STATIC / "singular-icon.svg",
        DASHBOARD_STATIC / "favicon.svg",
    ),
    CANONICAL_BRANDING / "singular-logo.svg": (DASHBOARD_STATIC / "singular-logo.svg",),
}


def main() -> None:
    for source, destinations in BRANDING_COPIES.items():
        for destination in destinations:
            shutil.copyfile(source, destination)
            print(f"Synchronized {destination.relative_to(REPOSITORY_ROOT)}")


if __name__ == "__main__":
    main()
