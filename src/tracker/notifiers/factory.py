from __future__ import annotations

from tracker.config import Settings
from tracker.notifiers.base import Notifier
from tracker.notifiers.console import ConsoleNotifier
from tracker.notifiers.email import EmailNotifier
from tracker.notifiers.multi import MultiNotifier
from tracker.notifiers.telegram import TelegramNotifier


def build_notifier(s: Settings) -> Notifier:
    channels: list[Notifier] = []
    if s.telegram_bot_token and s.telegram_chat_id:
        channels.append(TelegramNotifier(s.telegram_bot_token, s.telegram_chat_id))
    if s.smtp_host and s.email_from and s.email_recipients:
        channels.append(EmailNotifier(s.smtp_host, s.smtp_port, s.smtp_user, s.smtp_password,
                                      s.email_from, s.email_recipients, s.smtp_ssl))
    if not channels:
        channels.append(ConsoleNotifier())  # local default: print to terminal
    return MultiNotifier(channels)
