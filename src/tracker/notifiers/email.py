from __future__ import annotations

import smtplib
from collections.abc import Callable
from email.message import EmailMessage

from tracker.models import Message
from tracker.notifiers.base import NotifyError


class EmailNotifier:
    name = "email"

    def __init__(self, host: str, port: int, user: str | None, password: str | None,
                 sender: str, recipients: list[str], use_ssl: bool = False,
                 smtp_factory: Callable[..., smtplib.SMTP] | None = None):
        self.host, self.port, self.user, self.password = host, port, user, password
        self.sender, self.recipients, self.use_ssl = sender, recipients, use_ssl
        self._factory = smtp_factory

    def build(self, message: Message) -> EmailMessage:
        msg = EmailMessage()
        msg["Subject"] = message.subject
        msg["From"] = self.sender
        msg["To"] = ", ".join(self.recipients)
        msg.set_content(message.text)
        msg.add_alternative("<html><body style='font-family:sans-serif'>"
                            + message.html.replace("\n", "<br>") + "</body></html>", subtype="html")
        return msg

    def send(self, message: Message) -> None:
        factory = self._factory or (smtplib.SMTP_SSL if self.use_ssl else smtplib.SMTP)
        try:
            with factory(self.host, self.port, timeout=30) as smtp:
                if not self.use_ssl:
                    smtp.starttls()
                if self.user:
                    smtp.login(self.user, self.password or "")
                smtp.send_message(self.build(message))
        except (smtplib.SMTPException, OSError) as exc:
            raise NotifyError(f"email: {type(exc).__name__}: {exc}") from exc
