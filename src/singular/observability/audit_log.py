"""Audit logging with correlation identifiers and sensitive data redaction.

This module stores JSONL audit events with explicit correlation between
``event_id``, ``intent_id``, and ``action_id`` so sessions can be replayed
offline for diagnostics.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
import hashlib
import json
import os
import re
import uuid

_SENSITIVE_KEY_PATTERN = re.compile(
    r"(pass(word)?|secret|token|api[_-]?key|authorization|cookie|session|private[_-]?key|"
    r"credential|ssn|email|phone|address|iban|card|cvv|pwd)",
    re.IGNORECASE,
)

_EMAIL_PATTERN = re.compile(r"([A-Za-z0-9._%+-]+)@([A-Za-z0-9.-]+\.[A-Za-z]{2,})")
_LONG_TOKEN_PATTERN = re.compile(r"\b[A-Za-z0-9_\-]{20,}\b")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _stable_fingerprint(value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8", errors="ignore")).hexdigest()
    return f"sha256:{digest[:12]}"


def _redact_string(value: str) -> str:
    redacted = _EMAIL_PATTERN.sub("<redacted:email>", value)

    def _replace_token(match: re.Match[str]) -> str:
        token = match.group(0)
        if token.isdigit() and len(token) < 20:
            return token
        return f"<redacted:token:{_stable_fingerprint(token)}>"

    redacted = _LONG_TOKEN_PATTERN.sub(_replace_token, redacted)
    return redacted


def redact_sensitive_data(value: Any, key: str | None = None) -> Any:
    """Recursively redact sensitive information in mappings, lists and strings."""

    if key and _SENSITIVE_KEY_PATTERN.search(key):
        marker = "<redacted>"
        if isinstance(value, str) and value:
            marker = f"<redacted:{_stable_fingerprint(value)}>"
        return marker

    if isinstance(value, Mapping):
        return {str(k): redact_sensitive_data(v, str(k)) for k, v in value.items()}

    if isinstance(value, list):
        return [redact_sensitive_data(item) for item in value]

    if isinstance(value, tuple):
        return tuple(redact_sensitive_data(item) for item in value)

    if isinstance(value, str):
        return _redact_string(value)

    return value


@dataclass
class AuditLogStore:
    """JSONL-backed audit log with lineage correlation fields."""

    root: Path | str | None = None
    filename: str = "audit_events.jsonl"

    def __post_init__(self) -> None:
        base = Path(self.root) if self.root is not None else Path(os.environ.get("SINGULAR_HOME", "."))
        self.path = base / "mem" / self.filename
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _append(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        record = redact_sensitive_data(dict(payload))
        with self.path.open("a", encoding="utf-8") as output:
            output.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record

    def log(
        self,
        *,
        session_id: str,
        category: str,
        data: Mapping[str, Any],
        event_id: str | None = None,
        intent_id: str | None = None,
        action_id: str | None = None,
        timestamp: str | None = None,
    ) -> dict[str, Any]:
        """Append a generic audit event with full correlation lineage."""

        event_identifier = event_id or uuid.uuid4().hex
        payload = {
            "ts": timestamp or _now_iso(),
            "session_id": session_id,
            "category": category,
            "event_id": event_identifier,
            "intent_id": intent_id,
            "action_id": action_id,
            "data": dict(data),
        }
        return self._append(payload)

    def log_decision(
        self,
        *,
        session_id: str,
        decision: Mapping[str, Any],
        event_id: str | None = None,
        intent_id: str | None = None,
    ) -> dict[str, Any]:
        return self.log(
            session_id=session_id,
            category="decision",
            data=dict(decision),
            event_id=event_id,
            intent_id=intent_id,
        )

    def log_prompt(
        self,
        *,
        session_id: str,
        prompt: Mapping[str, Any],
        event_id: str,
        intent_id: str,
    ) -> dict[str, Any]:
        return self.log(
            session_id=session_id,
            category="prompt",
            data=dict(prompt),
            event_id=event_id,
            intent_id=intent_id,
        )

    def log_action(
        self,
        *,
        session_id: str,
        action: Mapping[str, Any],
        event_id: str,
        intent_id: str,
        action_id: str | None = None,
    ) -> dict[str, Any]:
        return self.log(
            session_id=session_id,
            category="action",
            data=dict(action),
            event_id=event_id,
            intent_id=intent_id,
            action_id=action_id or uuid.uuid4().hex,
        )

    def log_result(
        self,
        *,
        session_id: str,
        result: Mapping[str, Any],
        event_id: str,
        intent_id: str,
        action_id: str,
    ) -> dict[str, Any]:
        return self.log(
            session_id=session_id,
            category="result",
            data=dict(result),
            event_id=event_id,
            intent_id=intent_id,
            action_id=action_id,
        )


def read_audit_events(path: Path | str) -> list[dict[str, Any]]:
    """Read a JSONL audit file, skipping invalid lines."""

    events: list[dict[str, Any]] = []
    with Path(path).open(encoding="utf-8") as stream:
        for line in stream:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                events.append(parsed)
    return events


def filter_session(events: Iterable[Mapping[str, Any]], session_id: str) -> list[dict[str, Any]]:
    """Return only records for ``session_id`` preserving order."""

    return [dict(event) for event in events if event.get("session_id") == session_id]


__all__ = [
    "AuditLogStore",
    "filter_session",
    "read_audit_events",
    "redact_sensitive_data",
]
