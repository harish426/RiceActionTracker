import pytest

from tracker.config import Settings, load_sources
from tracker.snapshots import (
    GcsSnapshotStore,
    LocalSnapshotStore,
    NullSnapshotStore,
    build_snapshots,
)
from tracker.storage import build_storage
from tracker.storage.sqlite import SqliteStorage


def test_load_sources_defaults_and_validation(tmp_path):
    f = tmp_path / "s.yaml"
    f.write_text("sources:\n  - id: a\n    name: A\n    url: https://a\n")
    s = load_sources(f)[0]
    assert s.enabled and s.tier == 2 and s.verify_ssl and s.fetch_mode == "auto"


def test_duplicate_ids_rejected(tmp_path):
    f = tmp_path / "s.yaml"
    f.write_text("sources:\n  - {id: a, name: A, url: u}\n  - {id: a, name: B, url: v}\n")
    with pytest.raises(ValueError):
        load_sources(f)


def test_shipped_sources_file_is_valid():
    sources = load_sources("config/sources.yaml")
    assert sources and any(s.enabled for s in sources)


def test_settings_from_env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "abc")
    monkeypatch.setenv("STORAGE_BACKEND", "firestore")
    s = Settings(_env_file=None)
    assert s.telegram_bot_token == "abc" and s.storage_backend == "firestore"


def test_build_storage_sqlite_and_unknown(tmp_path):
    assert isinstance(build_storage(Settings(_env_file=None, sqlite_path=str(tmp_path / "x.db"))),
                      SqliteStorage)
    with pytest.raises(ValueError):
        build_storage(Settings(_env_file=None, storage_backend="mongo"))


def test_local_snapshot_writes_file(tmp_path):
    path = LocalSnapshotStore(str(tmp_path)).save("fci/home", "<html/>")
    assert open(path).read() == "<html/>" and "fci_home" in path


def test_gcs_snapshot_uploads_to_bucket():
    class Blob:
        def __init__(self, log, name): self.log, self.name = log, name
        def upload_from_string(self, c, content_type=None): self.log.append((self.name, c))

    class Bucket:
        name = "b"
        def __init__(self): self.log = []
        def blob(self, n): return Blob(self.log, n)

    b = Bucket()
    uri = GcsSnapshotStore(b).save("s", "data")
    assert uri.startswith("gs://b/s/") and b.log[0][1] == "data"


def test_snapshot_factory_choices(tmp_path):
    assert isinstance(build_snapshots(Settings(_env_file=None, snapshot_backend="none")), NullSnapshotStore)
    assert isinstance(build_snapshots(Settings(_env_file=None, snapshot_dir=str(tmp_path))), LocalSnapshotStore)
