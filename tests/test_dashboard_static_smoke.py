from __future__ import annotations

import re
from pathlib import Path

DASHBOARD_STATIC = Path("src/singular/dashboard/static")
DASHBOARD_TEMPLATE = Path("src/singular/dashboard/templates/dashboard.html")
AUDITED_JS = [
    DASHBOARD_STATIC / "bootstrap.js",
    DASHBOARD_STATIC / "actions.js",
    DASHBOARD_STATIC / "render-cockpit.js",
    DASHBOARD_STATIC / "render-lives.js",
    DASHBOARD_STATIC / "render-conversations.js",
    DASHBOARD_STATIC / "render-reflections.js",
]


def _ids_declared_in(text: str) -> set[str]:
    return set(re.findall(r"\bid=[\"']([^\"']+)[\"']", text))


def test_dashboard_bootstrap_literal_ids_exist_or_are_created() -> None:
    """Smoke check: bootstrap literal DOM IDs are backed by dashboard HTML or injected controls."""
    html_ids = _ids_declared_in(DASHBOARD_TEMPLATE.read_text(encoding="utf-8"))
    bootstrap = (DASHBOARD_STATIC / "bootstrap.js").read_text(encoding="utf-8")
    bootstrap_created_ids = _ids_declared_in(bootstrap)
    literal_refs = set(
        re.findall(r"document\.getElementById\([\"']([A-Za-z0-9_-]+)[\"']\)", bootstrap)
    )

    missing = literal_refs - html_ids - bootstrap_created_ids
    unprotected_missing = {
        element_id
        for element_id in missing
        if re.search(rf"document\.getElementById\([\"']{re.escape(element_id)}[\"']\)\.", bootstrap)
    }
    assert not unprotected_missing, (
        "Bootstrap references missing dashboard IDs without a guard: "
        f"{sorted(unprotected_missing)}"
    )


def test_dashboard_js_uses_guards_for_direct_get_element_access() -> None:
    """Smoke check: direct getElementById(...).property writes are replaced by guarded variables/helpers."""
    offenders: list[str] = []
    direct_access = re.compile(r"document\.getElementById\([^\n]+?\)\.(?!\?)")
    for path in AUDITED_JS:
      text = path.read_text(encoding="utf-8")
      for match in direct_access.finditer(text):
          line = text.count("\n", 0, match.start()) + 1
          offenders.append(f"{path}:{line}: {match.group(0)}")

    assert not offenders, "Unprotected direct DOM access remains:\n" + "\n".join(offenders)


def test_dashboard_quests_websocket_targets_existing_raw_panel() -> None:
    bootstrap = (DASHBOARD_STATIC / "bootstrap.js").read_text(encoding="utf-8")
    assert "getElementById('quests')" not in bootstrap
    assert "getElementById('quests-json-raw')" in bootstrap or "loadQuests()" in bootstrap
