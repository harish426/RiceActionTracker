import io

import httpx
import pytest
import respx
from pypdf import PdfWriter

from conftest import fixture_text
from tracker.fetchers import FetchError, HttpFetcher, LadderFetcher
from tracker.fetchers.ladder import looks_js_rendered
from tracker.fetchers.pdf import pdf_to_text
from tracker.fetchers.throttle import HostThrottle
from tracker.models import Source

SRC = Source(id="s", name="S", url="https://site.example/page")


def fetcher(**kw):
    return HttpFetcher("test-agent", retry_wait=0.0, **kw)


@respx.mock
def test_http_fetch_ok_sends_user_agent():
    route = respx.get(SRC.url).respond(200, html="<html>hi</html>")
    res = fetcher().fetch(SRC)
    assert res.text == "<html>hi</html>" and res.used == "http" and not res.is_pdf
    assert route.calls[0].request.headers["user-agent"] == "test-agent"


@respx.mock
def test_retries_on_5xx_then_succeeds():
    route = respx.get(SRC.url).mock(side_effect=[httpx.Response(503), httpx.Response(200, html="ok")])
    assert fetcher().fetch(SRC).text == "ok"
    assert route.call_count == 2


@respx.mock
def test_gives_up_after_attempts():
    route = respx.get(SRC.url).respond(500)
    with pytest.raises(FetchError):
        fetcher().fetch(SRC)
    assert route.call_count == 3


@respx.mock
def test_404_not_retried():
    route = respx.get(SRC.url).respond(404)
    with pytest.raises(FetchError):
        fetcher().fetch(SRC)
    assert route.call_count == 1


@respx.mock
def test_connection_error_becomes_fetch_error():
    respx.get(SRC.url).mock(side_effect=httpx.ConnectError("boom"))
    with pytest.raises(FetchError):
        fetcher().fetch(SRC)


def make_pdf_bytes() -> bytes:
    w = PdfWriter()
    w.add_blank_page(200, 200)
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


def test_pdf_to_text_handles_blank_and_garbage():
    assert pdf_to_text(make_pdf_bytes()) == ""
    assert pdf_to_text(b"not a pdf") == ""


@respx.mock
def test_pdf_source_detected_by_content_type():
    respx.get(SRC.url).respond(200, content=make_pdf_bytes(), headers={"content-type": "application/pdf"})
    assert fetcher().fetch(SRC).is_pdf


@respx.mock
def test_fetch_pdf_text_url():
    respx.get("https://site.example/a.pdf").respond(200, content=make_pdf_bytes())
    assert fetcher().fetch_pdf_text("https://site.example/a.pdf") == ""


def test_throttle_spaces_requests_per_host():
    now = [0.0]
    sleeps = []
    t = HostThrottle(2.0, clock=lambda: now[0], sleep=sleeps.append)
    t.wait("https://a.example/1")
    t.wait("https://a.example/2")
    t.wait("https://b.example/1")  # different host: no wait
    assert sleeps == [2.0]


def test_js_detection():
    assert looks_js_rendered(fixture_text("spa_shell.html"))
    assert not looks_js_rendered(fixture_text("fci_notices.html"))


class StubFetcher:
    def __init__(self, text, fail=False):
        self.text, self.fail, self.calls = text, fail, 0

    def fetch(self, source):
        from tracker.fetchers.base import FetchResult

        self.calls += 1
        if self.fail:
            raise FetchError("nope")
        return FetchResult(source.url, source.url, 200, "text/html", self.text, "browser")

    def fetch_pdf_text(self, url, verify_ssl=True):
        return ""


def test_ladder_uses_browser_for_js_page():
    http, browser = StubFetcher(fixture_text("spa_shell.html")), StubFetcher("<a href='/x'>rendered</a>")
    assert LadderFetcher(http, browser).fetch(SRC).used == "browser"
    assert browser.calls == 1


def test_ladder_skips_browser_for_normal_page():
    http, browser = StubFetcher(fixture_text("fci_notices.html")), StubFetcher("")
    LadderFetcher(http, browser).fetch(SRC)
    assert browser.calls == 0


def test_ladder_browser_failure_returns_http_result():
    http, browser = StubFetcher(fixture_text("spa_shell.html")), StubFetcher("", fail=True)
    assert LadderFetcher(http, browser).fetch(SRC).text == fixture_text("spa_shell.html")


def test_ladder_forced_browser_without_browser_errors():
    s = SRC.model_copy(update={"fetch_mode": "browser"})
    with pytest.raises(FetchError):
        LadderFetcher(StubFetcher("x"), None).fetch(s)
