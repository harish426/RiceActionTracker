from __future__ import annotations

import httpx

from tracker.models import Message
from tracker.notifiers.base import NotifyError

MAX_LEN = 4000  # Telegram limit is 4096


class TelegramNotifier:
    name = "telegram"

    def __init__(self, token: str, chat_id: str, client: httpx.Client | None = None):
        self.token = token
        self.chat_id = chat_id
        self.client = client or httpx.Client(timeout=20)

    def send(self, message: Message) -> None:
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        body = message.html[:MAX_LEN]
        try:
            resp = self.client.post(url, json={
                "chat_id": self.chat_id, "text": body, "parse_mode": "HTML",
                "disable_web_page_preview": True})
        except httpx.HTTPError as exc:
            raise NotifyError(f"telegram: {type(exc).__name__}") from exc  # never leak the token
        if resp.status_code != 200:
            raise NotifyError(f"telegram: HTTP {resp.status_code} {resp.text[:200]}")
