from __future__ import annotations

from tracker.extract import extract_candidates, page_text_length
from tracker.fetchers.base import Fetcher, FetchError, FetchResult
from tracker.models import Source

_JS_HINTS = ("enable javascript", "requires javascript", "noscript", "id=\"root\"", "id=\"app\"",
             "__next_data__", "ng-version")


def looks_js_rendered(html: str) -> bool:
    """Heuristic: lots of markup but almost no visible text and very few links."""
    low = html.lower()
    few_links = len(extract_candidates(html, "http://x", "")) <= 1
    thin = page_text_length(html) < 300
    return few_links and (thin or any(h in low for h in _JS_HINTS))


class LadderFetcher:
    """HTTP first; fall back to a real browser when the page looks JS-rendered."""

    def __init__(self, http: Fetcher, browser: Fetcher | None = None):
        self.http = http
        self.browser = browser

    def fetch(self, source: Source) -> FetchResult:
        if source.fetch_mode == "browser":
            if not self.browser:
                raise FetchError(f"{source.id}: fetch_mode=browser but browser is disabled "
                                 "(set BROWSER_ENABLED=true)")
            return self.browser.fetch(source)
        result = self.http.fetch(source)
        if source.fetch_mode == "auto" and self.browser and not result.is_pdf \
                and looks_js_rendered(result.text):
            try:
                return self.browser.fetch(source)
            except FetchError:
                return result  # better the thin HTTP page than nothing
        return result

    def fetch_pdf_text(self, url: str, verify_ssl: bool = True) -> str:
        return self.http.fetch_pdf_text(url, verify_ssl)
