from __future__ import annotations

import logging

from tracker.models import Message
from tracker.notifiers.base import Notifier, NotifyError

log = logging.getLogger(__name__)


class MultiNotifier:
    """Fan out to all channels. Succeeds if at least one channel delivered."""

    name = "multi"

    def __init__(self, notifiers: list[Notifier]):
        self.notifiers = notifiers

    def send(self, message: Message) -> None:
        errors: list[str] = []
        delivered = 0
        for n in self.notifiers:
            try:
                n.send(message)
                delivered += 1
            except NotifyError as exc:
                log.warning("notifier %s failed: %s", n.name, exc)
                errors.append(str(exc))
        if delivered == 0:
            raise NotifyError("; ".join(errors) or "no notifier configured")
