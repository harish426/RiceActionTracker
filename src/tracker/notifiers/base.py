from __future__ import annotations

from typing import Protocol

from tracker.models import Message


class NotifyError(Exception):
    """Raised when no channel could deliver a message."""


class Notifier(Protocol):
    name: str

    def send(self, message: Message) -> None: ...
