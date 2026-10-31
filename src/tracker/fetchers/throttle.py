from __future__ import annotations

import threading
import time
from urllib.parse import urlparse


class HostThrottle:
    """Guarantees a minimum gap between requests to the same host (politeness)."""

    def __init__(self, min_interval: float, clock=time.monotonic, sleep=time.sleep):
        self.min_interval = min_interval
        self._clock = clock
        self._sleep = sleep
        self._next_ok: dict[str, float] = {}
        self._lock = threading.Lock()

    def wait(self, url: str) -> None:
        host = urlparse(url).netloc
        with self._lock:
            now = self._clock()
            ready = self._next_ok.get(host, now)
            delay = max(0.0, ready - now)
            self._next_ok[host] = max(now, ready) + self.min_interval
        if delay:
            self._sleep(delay)
