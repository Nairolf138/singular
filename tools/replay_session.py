#!/usr/bin/env python3
"""Replay an offline audit session for diagnostics without live system access."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any
import argparse
import json
import sys

from observability.audit_log import filter_session, read_audit_events


def _load(path: Path, session_id: str) -> list[dict[str, Any]]:
    events = read_audit_events(path)
    if session_id:
        events = filter_session(events, session_id)
    return sorted(events, key=lambda row: str(row.get("ts", "")))


def _lineage_report(events: list[dict[str, Any]]) -> list[str]:
    issues: list[str] = []
    by_event: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_action: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)

    for row in events:
        event_id = str(row.get("event_id") or "")
        action_id = str(row.get("action_id") or "")
        if event_id:
            by_event[event_id].append(row)
            if action_id:
                by_action[(event_id, action_id)].append(row)

    for event_id, rows in by_event.items():
        categories = {str(item.get("category")) for item in rows}
        if "decision" not in categories:
            issues.append(f"event_id={event_id}: missing decision")
        if "action" in categories and "result" not in categories:
            issues.append(f"event_id={event_id}: action without result")

    for (event_id, action_id), rows in by_action.items():
        categories = {str(item.get("category")) for item in rows}
        if "action" not in categories:
            issues.append(f"event_id={event_id}, action_id={action_id}: result without action")

    return sorted(set(issues))


def _print_timeline(events: list[dict[str, Any]], verbose: bool) -> None:
    for index, row in enumerate(events, start=1):
        ts = row.get("ts", "?")
        category = row.get("category", "?")
        event_id = row.get("event_id", "-")
        intent_id = row.get("intent_id", "-")
        action_id = row.get("action_id", "-")
        print(f"[{index:04d}] {ts} | {category:<8} | event={event_id} intent={intent_id} action={action_id}")
        if verbose:
            print(json.dumps(row.get("data", {}), ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audit_log", type=Path, help="Path to audit_events.jsonl")
    parser.add_argument("--session-id", default="", help="Replay only one session")
    parser.add_argument("--verbose", action="store_true", help="Print full payloads")
    args = parser.parse_args(argv)

    if not args.audit_log.exists():
        print(f"error: audit file not found: {args.audit_log}", file=sys.stderr)
        return 2

    events = _load(args.audit_log, args.session_id)
    if not events:
        if args.session_id:
            print(f"No events found for session_id={args.session_id}")
        else:
            print("No events found")
        return 1

    _print_timeline(events, verbose=args.verbose)

    issues = _lineage_report(events)
    print("\n=== Diagnostics ===")
    if issues:
        for issue in issues:
            print(f"- {issue}")
        return 3

    print("- No lineage/correlation issue detected.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
