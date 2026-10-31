from conftest import FakeFetcher, RecordingNotifier, fixture_text
from tracker.models import Source
from tracker.pipeline import deliver_alert, process_source, retry_pending, run_sources

HTML = fixture_text("fci_notices.html")


def with_page(deps, source, page):
    deps.fetcher = FakeFetcher({source.url: page})
    return deps


def test_first_run_baselines_without_alerting(deps, source, notifier):
    with_page(deps, source, HTML)
    r = process_source(deps, source)
    assert r.baseline and r.alerts == 0 and r.items > 0
    assert notifier.sent == []
    assert deps.storage.get_state(source.id).baselined


def test_alert_existing_flag_alerts_on_first_run(deps, source, notifier):
    with_page(deps, source, HTML)
    r = process_source(deps, source, alert_existing=True)
    assert r.alerts == 1 and len(notifier.sent) == 1
    assert "Rice" in notifier.sent[0].subject


def test_new_rice_notice_alerts_exactly_once(deps, source, notifier):
    with_page(deps, source, HTML)
    process_source(deps, source)
    new_html = HTML.replace("</ul>", '<li><a href="/n/kerala-rice-eauction.pdf">E-Auction of Rice '
                            'at Kerala depots 20/11/2026</a></li></ul>')
    deps.fetcher.pages[source.url] = new_html
    r = process_source(deps, source)
    assert r.new_items == 1 and r.alerts == 1 and len(notifier.sent) == 1
    r2 = process_source(deps, source)  # nothing new now
    assert r2.new_items == 0 and len(notifier.sent) == 1


def test_irrelevant_and_wheat_notices_do_not_alert(deps, source, notifier):
    with_page(deps, source, HTML)
    process_source(deps, source)
    deps.fetcher.pages[source.url] = HTML.replace(
        "</ul>", '<li><a href="/w.pdf">OMSS wheat auction</a></li>'
        '<li><a href="/r.pdf">Recruitment notice</a></li></ul>')
    r = process_source(deps, source)
    assert r.new_items == 2 and r.alerts == 0 and notifier.sent == []


def test_same_auction_on_second_site_is_merged_not_duplicated(deps, notifier):
    from test_classify import FakeClient
    from tracker.classify import LLMClassifier

    payload = {"is_rice_auction": True, "confidence": 0.9, "summary": "s", "state": "Punjab",
               "auction_date": "2026-11-12", "quantity": "5000 MT"}
    deps.classifier = LLMClassifier(FakeClient(payload), "m")
    a = Source(id="a", name="A", url="https://a.example/")
    b = Source(id="b", name="B", url="https://b.example/")
    base = "<ul><li><a href='/old'>Old page link</a></li></ul>"
    deps.fetcher = FakeFetcher({a.url: base, b.url: base})
    process_source(deps, a)
    process_source(deps, b)
    deps.fetcher.pages[a.url] = base + "<a href='/x'>E-Auction rice Punjab</a>"
    deps.fetcher.pages[b.url] = base + "<a href='/y'>OMSS rice auction Punjab</a>"
    process_source(deps, a)
    process_source(deps, b)
    assert len(notifier.sent) == 1
    alert = deps.storage.recent_alerts()[0]
    assert sorted(alert.source_names) == ["A", "B"] and len(alert.urls) == 2


def test_pdf_with_vague_link_text_is_opened_and_classified(deps, source, notifier):
    base = "<ul><li><a href='/old'>old</a></li></ul>"
    deps.fetcher = FakeFetcher({source.url: base})
    process_source(deps, source)
    deps.fetcher.pages[source.url] = base + "<li><a href='/doc123.pdf'>Notice 123</a></li>"
    deps.fetcher.pdfs["https://fci.example/doc123.pdf"] = "E-Auction of Rice (OMSS) 5000 MT on 01/12/2026"
    r = process_source(deps, source)
    assert r.alerts == 1


def test_pdf_lookup_budget_is_respected(deps, source):
    deps.settings.pdf_lookup_limit = 1
    base = "<ul><li><a href='/old'>old</a></li></ul>"
    deps.fetcher = FakeFetcher({source.url: base})
    process_source(deps, source)
    deps.fetcher.pages[source.url] = base + "".join(
        f"<li><a href='/d{i}.pdf'>Notice {i}</a></li>" for i in range(3))
    for i in range(3):
        deps.fetcher.pdfs[f"https://fci.example/d{i}.pdf"] = "Rice e-auction"
    assert process_source(deps, source).alerts == 1  # only the first PDF was opened


def test_fetch_failure_recorded_and_health_alert_after_threshold(deps, source, notifier):
    deps.fetcher = FakeFetcher({source.url: Exception("timeout")})
    for _ in range(2):
        assert not process_source(deps, source).ok
    assert notifier.sent == []
    process_source(deps, source)
    assert len(notifier.sent) == 1 and "problem" in notifier.sent[0].subject.lower()
    process_source(deps, source)
    assert len(notifier.sent) == 1  # no spam


def test_recovery_notice_sent(deps, source, notifier):
    deps.fetcher = FakeFetcher({source.url: Exception("t")})
    for _ in range(3):
        process_source(deps, source)
    deps.fetcher.pages[source.url] = HTML
    process_source(deps, source)
    assert "recovered" in notifier.sent[-1].subject.lower()


def test_failed_notification_is_retried_next_run(deps, source):
    flaky = RecordingNotifier(fail=True)
    deps.notifier = flaky
    with_page(deps, source, HTML)
    process_source(deps, source)
    deps.fetcher.pages[source.url] = HTML.replace("</ul>", "<li><a href='/r.pdf'>Rice e-auction</a></li></ul>")
    process_source(deps, source)
    assert len(deps.storage.pending_alerts()) == 1
    flaky.fail = False
    assert retry_pending(deps) == 1
    assert deps.storage.pending_alerts() == [] and len(flaky.sent) == 1


def test_zero_candidates_first_run_does_not_baseline(deps, source):
    with_page(deps, source, "")
    process_source(deps, source)
    assert not deps.storage.get_state(source.id).baselined


def test_run_sources_isolates_failures(deps, source):
    good = source
    bad = Source(id="bad", name="Bad", url="https://bad.example/")
    deps.fetcher = FakeFetcher({good.url: HTML, bad.url: Exception("down")})
    report = run_sources(deps, [good, bad])
    assert [r.ok for r in report.sources] == [True, False]
    assert len(report.failed) == 1


def test_run_sources_survives_unexpected_exception(deps, source):
    deps.fetcher = FakeFetcher({})  # KeyError inside fetch
    report = run_sources(deps, [source])
    assert not report.sources[0].ok and "KeyError" in report.sources[0].error


def test_deliver_alert_marks_notified(deps):
    from tracker.models import Alert

    a = Alert(key="z", title="t", urls=["u"], source_names=["s"])
    assert deliver_alert(deps, a) and deps.storage.get_alert("z").notified
