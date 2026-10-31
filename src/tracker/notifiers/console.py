from __future__ import annotations

from tracker.models import Message


class ConsoleNotifier:
    name = "console"

    def __init__(self, out=print):
        self.out = out

    def send(self, message: Message) -> None:
        self.out(f"\n=== {message.subject} ===\n{message.text}\n")
