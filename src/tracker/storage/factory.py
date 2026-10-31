from __future__ import annotations

from tracker.config import Settings
from tracker.storage.base import Storage


def build_storage(settings: Settings) -> Storage:
    if settings.storage_backend == "firestore":
        from tracker.storage.firestore import FirestoreStorage

        return FirestoreStorage.from_settings(settings.google_cloud_project,
                                              settings.firestore_database)
    if settings.storage_backend == "sqlite":
        from tracker.storage.sqlite import SqliteStorage

        return SqliteStorage(settings.sqlite_path)
    raise ValueError(f"Unknown STORAGE_BACKEND: {settings.storage_backend}")
