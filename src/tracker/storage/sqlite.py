from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from tracker.models import Alert, Candidate, SourceState, utcnow


class SqliteStorage:
    def __init__(self, path: str):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock, self._conn:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS source_state (source_id TEXT PRIMARY KEY, json TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS seen (
                    source_id TEXT NOT NULL, fingerprint TEXT NOT NULL,
                    title TEXT, url TEXT, first_seen TEXT NOT NULL,
                    PRIMARY KEY (source_id, fingerprint));
                CREATE TABLE IF NOT EXISTS alerts (
                    key TEXT PRIMARY KEY, notified INTEGER NOT NULL,
                    created_at TEXT NOT NULL, json TEXT NOT NULL);
                """
            )

    def get_state(self, source_id: str) -> SourceState:
        with self._lock:
            row = self._conn.execute("SELECT json FROM source_state WHERE source_id=?",
                                     (source_id,)).fetchone()
        return SourceState.model_validate_json(row[0]) if row else SourceState(source_id=source_id)

    def save_state(self, state: SourceState) -> None:
        with self._lock, self._conn:
            self._conn.execute("INSERT OR REPLACE INTO source_state VALUES (?, ?)",
                               (state.source_id, state.model_dump_json()))

    def list_states(self) -> list[SourceState]:
        with self._lock:
            rows = self._conn.execute("SELECT json FROM source_state ORDER BY source_id").fetchall()
        return [SourceState.model_validate_json(r[0]) for r in rows]

    def seen_fingerprints(self, source_id: str) -> set[str]:
        with self._lock:
            rows = self._conn.execute("SELECT fingerprint FROM seen WHERE source_id=?",
                                      (source_id,)).fetchall()
        return {r[0] for r in rows}

    def add_seen(self, source_id: str, items: list[Candidate]) -> None:
        now = utcnow().isoformat()
        with self._lock, self._conn:
            self._conn.executemany(
                "INSERT OR IGNORE INTO seen VALUES (?, ?, ?, ?, ?)",
                [(source_id, c.fingerprint, c.title[:300], c.url, now) for c in items])

    def get_alert(self, key: str) -> Alert | None:
        with self._lock:
            row = self._conn.execute("SELECT json FROM alerts WHERE key=?", (key,)).fetchone()
        return Alert.model_validate_json(row[0]) if row else None

    def save_alert(self, alert: Alert) -> None:
        with self._lock, self._conn:
            self._conn.execute("INSERT OR REPLACE INTO alerts VALUES (?, ?, ?, ?)",
                               (alert.key, int(alert.notified), alert.created_at.isoformat(),
                                alert.model_dump_json()))

    def pending_alerts(self) -> list[Alert]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT json FROM alerts WHERE notified=0 ORDER BY created_at").fetchall()
        return [Alert.model_validate_json(r[0]) for r in rows]

    def recent_alerts(self, limit: int = 20) -> list[Alert]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT json FROM alerts ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [Alert.model_validate_json(r[0]) for r in rows]
