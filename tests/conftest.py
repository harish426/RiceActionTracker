from __future__ import annotations

from pathlib import Path

import pytest

from tracker.classify import KeywordClassifier
from tracker.config import Settings
from tracker.models import Message, Source
from tracker.pipeline import Deps
from tracker.snapshots import NullSnapshotStore
from tracker.storage.sqlite import SqliteStorage

FIXTURES = Path(__file__).parent / "fixtures"


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class RecordingNotifier:
    name = "recording"

    def __init__(self, fail: bool = False):
        self.sent: list[Message] = []
        self.fail = fail

    def send(self, message: Message) -> None:
        from tracker.notifiers.base import NotifyError

        if self.fail:
            raise NotifyError("down")
        self.sent.append(message)


class FakeFetcher:
    """Serves pages from a dict; raises FetchError for urls mapped to an Exception."""

    def __init__(self, pages: dict[str, object] | None = None):
        self.pages = pages or {}
        self.pdfs: dict[str, str] = {}

    def fetch(self, source: Source):
        from tracker.fetchers.base import FetchError, FetchResult

        page = self.pages[source.url]
        if isinstance(page, Exception):
            raise FetchError(str(page))
        return FetchResult(source.url, source.url, 200, "text/html", page, "http")

    def fetch_pdf_text(self, url: str, verify_ssl: bool = True) -> str:
        return self.pdfs.get(url, "")


@pytest.fixture
def source() -> Source:
    return Source(id="fci", name="FCI", url="https://fci.example/notices", state=None)


@pytest.fixture
def notifier() -> RecordingNotifier:
    return RecordingNotifier()


@pytest.fixture
def deps(notifier) -> Deps:
    return Deps(settings=Settings(_env_file=None), storage=SqliteStorage(":memory:"),
                fetcher=FakeFetcher(), classifier=KeywordClassifier(), notifier=notifier,
                snapshots=NullSnapshotStore())
