"""Headless-browser fetcher for JavaScript-rendered portals (optional dependency)."""

from __future__ import annotations

from tracker.fetchers.base import FetchError, FetchResult
from tracker.models import Source


class BrowserFetcher:
    def __init__(self, user_agent: str, timeout: float = 45.0):
        self.user_agent = user_agent
        self.timeout = timeout

    def fetch(self, source: Source) -> FetchResult:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:  # pragma: no cover - depends on optional install
            raise FetchError(
                "Playwright not installed. Run: pip install '.[browser]' && playwright install chromium"
            ) from exc
        try:  # pragma: no cover - needs a real browser
            with sync_playwright() as p:
                browser = p.chromium.launch(args=["--no-sandbox"])
                ctx = browser.new_context(user_agent=self.user_agent,
                                          ignore_https_errors=not source.verify_ssl)
                page = ctx.new_page()
                resp = page.goto(source.url, wait_until="networkidle",
                                 timeout=int(self.timeout * 1000))
                html = page.content()
                status = resp.status if resp else 200
                final = page.url
                browser.close()
            return FetchResult(source.url, final, status, "text/html", html, "browser")
        except Exception as exc:  # pragma: no cover
            raise FetchError(f"{source.url}: browser fetch failed: {exc}") from exc
