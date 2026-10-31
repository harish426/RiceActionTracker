from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from tracker.models import Source


class FetchError(Exception):
    """Raised when a page could not be retrieved."""


@dataclass
class FetchResult:
    url: str
    final_url: str
    status: int
    content_type: str
    text: str  # HTML, or extracted text for PDFs
    used: str  # http | browser
    is_pdf: bool = False


class Fetcher(Protocol):
    def fetch(self, source: Source) -> FetchResult: ...

    def fetch_pdf_text(self, url: str, verify_ssl: bool = True) -> str: ...
