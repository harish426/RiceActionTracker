import pytest

from fake_firestore import FakeFirestore
from tracker.models import Alert, Candidate, SourceState
from tracker.storage.firestore import FirestoreStorage
from tracker.storage.sqlite import SqliteStorage


@pytest.fixture(params=["sqlite", "firestore"])
def store(request):
    return SqliteStorage(":memory:") if request.param == "sqlite" else FirestoreStorage(FakeFirestore())


def test_state_roundtrip_and_default(store):
    assert store.get_state("a").baselined is False
    store.save_state(SourceState(source_id="a", baselined=True, last_item_count=7))
    got = store.get_state("a")
    assert got.baselined and got.last_item_count == 7
    assert [s.source_id for s in store.list_states()] == ["a"]


def test_seen_is_per_source_and_idempotent(store):
    c = Candidate(title="t", url="https://x")
    store.add_seen("a", [c])
    store.add_seen("a", [c])
    assert store.seen_fingerprints("a") == {c.fingerprint}
    assert store.seen_fingerprints("b") == set()


def test_alert_lifecycle(store):
    a = Alert(key="k1", title="T", urls=["u"])
    assert store.get_alert("k1") is None
    store.save_alert(a)
    assert [x.key for x in store.pending_alerts()] == ["k1"]
    a.notified = True
    store.save_alert(a)
    assert store.pending_alerts() == []
    assert store.get_alert("k1").notified
    assert [x.key for x in store.recent_alerts()] == ["k1"]
