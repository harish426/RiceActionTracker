from tracker.health import record_failure, record_success
from tracker.models import SourceState


def test_failure_alerts_once_at_threshold():
    s = SourceState(source_id="a")
    assert record_failure(s, "e", 3) is None
    assert record_failure(s, "e", 3) is None
    assert "3 times" in record_failure(s, "boom", 3)
    assert record_failure(s, "boom", 3) is None  # no spam


def test_recovery_after_alert():
    s = SourceState(source_id="a")
    for _ in range(3):
        record_failure(s, "e", 3)
    problem, recovered = record_success(s, 10)
    assert problem is None and recovered and not s.health_alerted and s.consecutive_failures == 0


def test_no_recovery_message_without_prior_alert():
    s = SourceState(source_id="a")
    record_failure(s, "e", 3)
    assert record_success(s, 10) == (None, False)


def test_sudden_item_drop_flags_layout_change_once_and_recovers():
    s = SourceState(source_id="a", baselined=True, last_item_count=50)
    problem, rec = record_success(s, 2)
    assert "layout" in problem and not rec
    assert s.last_item_count == 50  # expectation preserved
    assert record_success(s, 2) == (None, False)  # still broken, no repeat alert
    assert record_success(s, 48) == (None, True)  # back to normal


def test_small_pages_do_not_trigger_drop_alert():
    s = SourceState(source_id="a", baselined=True, last_item_count=4)
    assert record_success(s, 0) == (None, False)
