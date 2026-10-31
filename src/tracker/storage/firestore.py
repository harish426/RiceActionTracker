"""Firestore storage for Google Cloud. Same interface as SqliteStorage.

Layout:  source_state/{source_id}   alerts/{key}   seen_{source_id}/{fingerprint}
"""

from __future__ import annotations

import json
from typing import Any

from tracker.models import Alert, Candidate, SourceState, utcnow


class FirestoreStorage:
    def __init__(self, client: Any):
        self.db = client

    @classmethod
    def from_settings(cls, project: str | None, database: str = "(default)") -> FirestoreStorage:
        from google.cloud import firestore  # lazy: only needed on GCP

        return cls(firestore.Client(project=project, database=database))

    def get_state(self, source_id: str) -> SourceState:
        snap = self.db.collection("source_state").document(source_id).get()
        return SourceState.model_validate_json(snap.to_dict()["json"]) if snap.exists \
            else SourceState(source_id=source_id)

    def save_state(self, state: SourceState) -> None:
        self.db.collection("source_state").document(state.source_id).set(
            {"json": state.model_dump_json()})

    def list_states(self) -> list[SourceState]:
        docs = self.db.collection("source_state").stream()
        return sorted((SourceState.model_validate_json(d.to_dict()["json"]) for d in docs),
                      key=lambda s: s.source_id)

    def _seen(self, source_id: str):
        return self.db.collection(f"seen_{source_id}")

    def seen_fingerprints(self, source_id: str) -> set[str]:
        return {d.id for d in self._seen(source_id).stream()}

    def add_seen(self, source_id: str, items: list[Candidate]) -> None:
        now = utcnow().isoformat()
        for c in items:
            self._seen(source_id).document(c.fingerprint).set(
                {"title": c.title[:300], "url": c.url, "first_seen": now})

    def get_alert(self, key: str) -> Alert | None:
        snap = self.db.collection("alerts").document(key).get()
        return Alert.model_validate_json(snap.to_dict()["json"]) if snap.exists else None

    def save_alert(self, alert: Alert) -> None:
        self.db.collection("alerts").document(alert.key).set(
            {"json": alert.model_dump_json(), "notified": alert.notified,
             "created_at": alert.created_at.isoformat()})

    def _alerts(self) -> list[Alert]:
        return [Alert.model_validate(json.loads(d.to_dict()["json"]))
                for d in self.db.collection("alerts").stream()]

    def pending_alerts(self) -> list[Alert]:
        return sorted((a for a in self._alerts() if not a.notified), key=lambda a: a.created_at)

    def recent_alerts(self, limit: int = 20) -> list[Alert]:
        return sorted(self._alerts(), key=lambda a: a.created_at, reverse=True)[:limit]
