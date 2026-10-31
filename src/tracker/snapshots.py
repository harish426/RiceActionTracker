"""Raw page snapshots (for debugging 'why did it miss this?'). Local folder or GCS."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Protocol

from tracker.config import Settings
from tracker.models import utcnow


class SnapshotStore(Protocol):
    def save(self, source_id: str, content: str) -> str: ...


def _name(source_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", source_id)
    return f"{safe}/{utcnow().strftime('%Y%m%dT%H%M%S')}.html"


class LocalSnapshotStore:
    def __init__(self, root: str):
        self.root = Path(root)

    def save(self, source_id: str, content: str) -> str:
        path = self.root / _name(source_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return str(path)


class GcsSnapshotStore:
    def __init__(self, bucket: Any):
        self.bucket = bucket

    def save(self, source_id: str, content: str) -> str:
        name = _name(source_id)
        self.bucket.blob(name).upload_from_string(content, content_type="text/html")
        return f"gs://{self.bucket.name}/{name}"


class NullSnapshotStore:
    def save(self, source_id: str, content: str) -> str:
        return ""


def build_snapshots(settings: Settings) -> SnapshotStore:
    if settings.snapshot_backend == "none":
        return NullSnapshotStore()
    if settings.snapshot_backend == "gcs":
        from google.cloud import storage

        client = storage.Client(project=settings.google_cloud_project)
        return GcsSnapshotStore(client.bucket(settings.gcs_bucket))
    return LocalSnapshotStore(settings.snapshot_dir)
