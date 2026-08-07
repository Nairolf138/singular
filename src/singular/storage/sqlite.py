"""SQLite repositories for durable Singular state.

The repositories intentionally keep legacy JSON/JSONL files readable during the
transition. Writes go to SQLite and, when ``compat_json`` is enabled, can still be
mirrored by callers to their existing files.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import sqlite3
from typing import Any, Mapping

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class StorageConfig:
    root: Path
    db_path: Path | None = None
    compat_json: bool = True

    @property
    def database(self) -> Path:
        return self.db_path or (self.root / "mem" / "singular.sqlite3")


class SQLiteStorage:
    def __init__(self, config: StorageConfig | Path | str) -> None:
        if isinstance(config, StorageConfig):
            self.config = config
        else:
            self.config = StorageConfig(root=Path(config))
        self.db_path = self.config.database
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._migrate()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _migrate(self) -> None:
        with self.connect() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT DEFAULT CURRENT_TIMESTAMP)"
            )
            applied = {
                row[0] for row in conn.execute("SELECT version FROM schema_migrations")
            }
            if SCHEMA_VERSION not in applied:
                conn.executescript("""
                    CREATE TABLE IF NOT EXISTS episodes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        ts TEXT,
                        event TEXT,
                        payload_json TEXT NOT NULL,
                        source_path TEXT,
                        source_line INTEGER,
                        UNIQUE(source_path, source_line)
                    );
                    CREATE TABLE IF NOT EXISTS world_state_snapshots (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        ts TEXT DEFAULT CURRENT_TIMESTAMP,
                        payload_json TEXT NOT NULL,
                        source_path TEXT,
                        UNIQUE(source_path, ts)
                    );
                    CREATE TABLE IF NOT EXISTS run_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        run_id TEXT NOT NULL,
                        ts TEXT,
                        event_type TEXT,
                        payload_json TEXT NOT NULL,
                        source_path TEXT,
                        source_line INTEGER,
                        UNIQUE(source_path, source_line)
                    );
                    CREATE INDEX IF NOT EXISTS idx_run_events_run ON run_events(run_id);
                    CREATE INDEX IF NOT EXISTS idx_run_events_ts ON run_events(ts);
                    CREATE INDEX IF NOT EXISTS idx_run_events_type ON run_events(event_type);
                    CREATE TABLE IF NOT EXISTS provider_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        ts TEXT DEFAULT CURRENT_TIMESTAMP,
                        provider TEXT NOT NULL,
                        active_provider TEXT,
                        latency_ms REAL,
                        fallback INTEGER NOT NULL DEFAULT 0,
                        error_category TEXT,
                        llm_real INTEGER NOT NULL DEFAULT 0,
                        payload_json TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS skill_scores (
                        skill TEXT PRIMARY KEY,
                        success_rate REAL NOT NULL DEFAULT 0,
                        mean_cost REAL NOT NULL DEFAULT 0,
                        recent_failures INTEGER NOT NULL DEFAULT 0,
                        mean_quality REAL NOT NULL DEFAULT 0,
                        mean_satisfaction REAL NOT NULL DEFAULT 0,
                        use_count INTEGER NOT NULL DEFAULT 0,
                        quarantined INTEGER NOT NULL DEFAULT 0,
                        quarantine_reason TEXT,
                        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        payload_json TEXT NOT NULL
                    );
                    """)
                conn.execute(
                    "INSERT OR IGNORE INTO schema_migrations(version) VALUES (?)",
                    (SCHEMA_VERSION,),
                )
            # Existing version-1 databases predate the dashboard query indexes.
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_run_events_run ON run_events(run_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_run_events_ts ON run_events(ts)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_run_events_type ON run_events(event_type)"
            )


def _dump(payload: Mapping[str, Any]) -> str:
    return json.dumps(dict(payload), ensure_ascii=False, sort_keys=True)


def _row_payload(row: sqlite3.Row) -> dict[str, Any]:
    payload = json.loads(row["payload_json"])
    return payload if isinstance(payload, dict) else {"value": payload}


class EpisodesRepository:
    def __init__(self, storage: SQLiteStorage) -> None:
        self.storage = storage

    def add(
        self,
        payload: Mapping[str, Any],
        *,
        source_path: str | None = None,
        source_line: int | None = None,
    ) -> None:
        with self.storage.connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO episodes(ts,event,payload_json,source_path,source_line) VALUES (?,?,?,?,?)",
                (
                    payload.get("ts"),
                    payload.get("event"),
                    _dump(payload),
                    source_path,
                    source_line,
                ),
            )

    def list(self) -> list[dict[str, Any]]:
        with self.storage.connect() as conn:
            return [
                _row_payload(r)
                for r in conn.execute("SELECT payload_json FROM episodes ORDER BY id")
            ]


class WorldStateRepository:
    def __init__(self, storage: SQLiteStorage) -> None:
        self.storage = storage

    def save_snapshot(
        self, payload: Mapping[str, Any], *, source_path: str | None = None
    ) -> None:
        ts = str(payload.get("ts") or payload.get("updated_at") or "") or None
        with self.storage.connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO world_state_snapshots(ts,payload_json,source_path) VALUES (COALESCE(?, CURRENT_TIMESTAMP),?,?)",
                (ts, _dump(payload), source_path),
            )

    def latest(self) -> dict[str, Any] | None:
        with self.storage.connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM world_state_snapshots ORDER BY id DESC LIMIT 1"
            ).fetchone()
            return _row_payload(row) if row else None


class RunsRepository:
    def __init__(self, storage: SQLiteStorage) -> None:
        self.storage = storage

    def add_event(
        self,
        run_id: str,
        payload: Mapping[str, Any],
        *,
        event_type: str | None = None,
        source_path: str | None = None,
        source_line: int | None = None,
    ) -> None:
        with self.storage.connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO run_events(run_id,ts,event_type,payload_json,source_path,source_line) VALUES (?,?,?,?,?,?)",
                (
                    run_id,
                    payload.get("ts") or payload.get("_ts"),
                    event_type or payload.get("event") or payload.get("_event_type"),
                    _dump(payload),
                    source_path,
                    source_line,
                ),
            )

    def list_events(
        self,
        run_id: str | None = None,
        *,
        event_type: str | None = None,
        limit: int = 10_000,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        sql = (
            "SELECT payload_json, run_id FROM run_events"
            + (
                " WHERE "
                + " AND ".join(
                    filter(
                        None,
                        [
                            "run_id=?" if run_id else "",
                            "event_type=?" if event_type else "",
                        ],
                    )
                )
                if run_id or event_type
                else ""
            )
            + " ORDER BY id LIMIT ? OFFSET ?"
        )
        args = tuple(value for value in (run_id, event_type) if value is not None) + (
            max(1, limit),
            max(0, offset),
        )
        with self.storage.connect() as conn:
            rows = conn.execute(sql, args).fetchall()
            out = []
            for r in rows:
                payload = _row_payload(r)
                payload.setdefault("_run_file", r["run_id"])
                out.append(payload)
            return out


class ProviderEventsRepository:
    def __init__(self, storage: SQLiteStorage) -> None:
        self.storage = storage

    def add(self, payload: Mapping[str, Any]) -> None:
        with self.storage.connect() as conn:
            conn.execute(
                "INSERT INTO provider_events(provider,active_provider,latency_ms,fallback,error_category,llm_real,payload_json) VALUES (?,?,?,?,?,?,?)",
                (
                    payload.get("provider", "unknown"),
                    payload.get("active_provider"),
                    payload.get("latency_ms"),
                    int(bool(payload.get("fallback"))),
                    payload.get("error_category"),
                    int(bool(payload.get("llm_real"))),
                    _dump(payload),
                ),
            )


class SkillScoresRepository:
    def __init__(self, storage: SQLiteStorage) -> None:
        self.storage = storage

    def upsert(
        self,
        skill: str,
        stats: Mapping[str, Any],
        *,
        quarantined: bool = False,
        quarantine_reason: str | None = None,
    ) -> None:
        payload = {
            **dict(stats),
            "skill": skill,
            "quarantined": quarantined,
            "quarantine_reason": quarantine_reason,
        }
        with self.storage.connect() as conn:
            conn.execute(
                """INSERT INTO skill_scores(skill,success_rate,mean_cost,recent_failures,mean_quality,mean_satisfaction,use_count,quarantined,quarantine_reason,payload_json)
            VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(skill) DO UPDATE SET success_rate=excluded.success_rate, mean_cost=excluded.mean_cost, recent_failures=excluded.recent_failures, mean_quality=excluded.mean_quality, mean_satisfaction=excluded.mean_satisfaction, use_count=excluded.use_count, quarantined=excluded.quarantined, quarantine_reason=excluded.quarantine_reason, updated_at=CURRENT_TIMESTAMP, payload_json=excluded.payload_json""",
                (
                    skill,
                    float(stats.get("success_rate", 0)),
                    float(stats.get("mean_cost", 0)),
                    int(stats.get("recent_failures", 0)),
                    float(stats.get("mean_quality", 0)),
                    float(stats.get("mean_satisfaction", 0)),
                    int(stats.get("use_count", 0)),
                    int(quarantined),
                    quarantine_reason,
                    _dump(payload),
                ),
            )

    def get(self, skill: str) -> dict[str, Any] | None:
        with self.storage.connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM skill_scores WHERE skill=?", (skill,)
            ).fetchone()
            return _row_payload(row) if row else None
