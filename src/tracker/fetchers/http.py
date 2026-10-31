from __future__ import annotations

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from tracker.fetchers.base import FetchError, FetchResult
from tracker.fetchers.pdf import pdf_to_text
from tracker.fetchers.throttle import HostThrottle
from tracker.models import Source


def _retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TransportError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        return code == 429 or code >= 500
    return False


class HttpFetcher:
    def __init__(self, user_agent: str, timeout: float = 30.0, throttle: HostThrottle | None = None,
                 retry_wait: float = 1.0, attempts: int = 3):
        self.user_agent = user_agent
        self.timeout = timeout
        self.throttle = throttle
        self._attempts = attempts
        self._retry_wait = retry_wait

    def _get(self, url: str, verify: bool) -> httpx.Response:
        @retry(
            retry=retry_if_exception(_retryable),
            stop=stop_after_attempt(self._attempts),
            wait=wait_exponential(multiplier=self._retry_wait, max=15),
            reraise=True,
        )
        def attempt() -> httpx.Response:
            if self.throttle:
                self.throttle.wait(url)
            with httpx.Client(
                headers={"User-Agent": self.user_agent, "Accept-Language": "en-IN,en;q=0.9,hi;q=0.8"},
                timeout=self.timeout, follow_redirects=True, verify=verify,
            ) as client:
                resp = client.get(url)
                resp.raise_for_status()
                return resp

        try:
            return attempt()
        except httpx.HTTPError as exc:
            raise FetchError(f"{url}: {type(exc).__name__}: {exc}") from exc

    def fetch(self, source: Source) -> FetchResult:
        resp = self._get(source.url, source.verify_ssl)
        ctype = resp.headers.get("content-type", "").lower()
        is_pdf = "pdf" in ctype or source.url.lower().split("?")[0].endswith(".pdf")
        text = pdf_to_text(resp.content) if is_pdf else resp.text
        return FetchResult(source.url, str(resp.url), resp.status_code, ctype, text, "http", is_pdf)

    def fetch_pdf_text(self, url: str, verify_ssl: bool = True) -> str:
        return pdf_to_text(self._get(url, verify_ssl).content)
