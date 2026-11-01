import httpx
import pytest
import respx

from conftest import RecordingNotifier
from tracker.config import Settings
from tracker.models import Alert, SourceState
from tracker.notifiers import NotifyError, build_notifier
from tracker.notifiers.console import ConsoleNotifier
from tracker.notifiers.email import EmailNotifier
from tracker.notifiers.messages import format_alert, format_digest, format_health
from tracker.notifiers.multi import MultiNotifier
from tracker.notifiers.telegram import TelegramNotifier

ALERT = Alert(key="k", commodity="rice", title="Rice <OMSS> & more", urls=["https://x/a?b=1&c=2"], source_names=["FCI"],
              state="Punjab", auction_date="2026-11-12", quantity="5000 MT", summary="Sale", method="llm")


def test_format_alert_escapes_html_and_has_fields():
    m = format_alert(ALERT)
    assert "&lt;OMSS&gt;" in m.html and "<OMSS>" not in m.html
    assert "Punjab" in m.text and "5000 MT" in m.text
    assert 'href="https://x/a?b=1&amp;c=2"' in m.html
    assert "verify" not in m.text  # LLM result: no keyword caveat


def test_keyword_alert_has_verify_caveat():
    assert "verify" in format_alert(ALERT.model_copy(update={"method": "keyword"})).text


def test_health_and_digest_messages():
    assert "recovered" in format_health("S", "ok", recovered=True).subject.lower()
    st = [SourceState(source_id="a", consecutive_failures=3, last_error="x"),
          SourceState(source_id="b", last_success=ALERT.created_at)]
    d = format_digest(st, {"a": "Alpha"}, 4)
    assert "1/2" in d.text and "Alpha" in d.text


@respx.mock
def test_telegram_success_payload():
    route = respx.post("https://api.telegram.org/botTOK/sendMessage").respond(200, json={"ok": True})
    TelegramNotifier("TOK", "123").send(format_alert(ALERT))
    body = route.calls[0].request.content.decode()
    assert '"chat_id":"123"' in body.replace(" ", "") and "HTML" in body


@respx.mock
def test_telegram_http_error_raises_without_leaking_token():
    respx.post("https://api.telegram.org/botTOK/sendMessage").mock(side_effect=httpx.ConnectError("x"))
    with pytest.raises(NotifyError) as e:
        TelegramNotifier("TOK", "123").send(format_alert(ALERT))
    assert "TOK" not in str(e.value)


@respx.mock
def test_telegram_non_200_raises():
    respx.post("https://api.telegram.org/botTOK/sendMessage").respond(400, json={"ok": False})
    with pytest.raises(NotifyError):
        TelegramNotifier("TOK", "123").send(format_alert(ALERT))


class FakeSMTP:
    instances = []

    def __init__(self, host, port, timeout=None):
        self.host, self.port, self.sent, self.tls, self.login_args = host, port, [], False, None
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self):
        self.tls = True

    def login(self, u, p):
        self.login_args = (u, p)

    def send_message(self, msg):
        self.sent.append(msg)


def test_email_sends_multipart_with_starttls_and_login():
    FakeSMTP.instances.clear()
    n = EmailNotifier("smtp.x", 587, "u", "p", "from@x", ["a@x", "b@x"], smtp_factory=FakeSMTP)
    n.send(format_alert(ALERT))
    smtp = FakeSMTP.instances[0]
    msg = smtp.sent[0]
    assert smtp.tls and smtp.login_args == ("u", "p")
    assert msg["To"] == "a@x, b@x" and msg["Subject"].startswith("[RICE]")
    assert msg.get_body(("html",)) is not None and msg.get_body(("plain",)) is not None


def test_email_smtp_failure_raises_notify_error():
    def boom(*a, **k):
        raise OSError("refused")

    with pytest.raises(NotifyError):
        EmailNotifier("h", 25, None, None, "f@x", ["t@x"], smtp_factory=boom).send(format_alert(ALERT))


class Failing:
    name = "failing"

    def send(self, m):
        raise NotifyError("down")


def test_multi_succeeds_if_any_channel_works():
    ok = RecordingNotifier()
    MultiNotifier([Failing(), ok]).send(format_alert(ALERT))
    assert len(ok.sent) == 1


def test_multi_raises_if_all_fail():
    with pytest.raises(NotifyError):
        MultiNotifier([Failing(), Failing()]).send(format_alert(ALERT))


def test_console_notifier_prints():
    out = []
    ConsoleNotifier(out.append).send(format_alert(ALERT))
    assert "Punjab" in out[0]


def test_factory_defaults_to_console_and_builds_configured_channels():
    s = Settings(_env_file=None)
    assert [n.name for n in build_notifier(s).notifiers] == ["console"]
    s = Settings(_env_file=None, telegram_bot_token="t", telegram_chat_id="1", smtp_host="h",
                 email_from="f@x", email_to="a@x, b@x")
    assert [n.name for n in build_notifier(s).notifiers] == ["telegram", "email"]
    assert s.email_recipients == ["a@x", "b@x"]


def test_commodity_is_clearly_labelled_in_every_channel():
    rice = format_alert(ALERT)
    maize = format_alert(ALERT.model_copy(update={"commodity": "maize", "notice_type": "tender"}))
    assert rice.subject.startswith("[RICE]") and "🌾" in rice.html and rice.text.startswith("RICE AUCTION")
    assert maize.subject.startswith("[MAIZE] Tender") and "🌽" in maize.html
    assert maize.text.startswith("MAIZE TENDER") and "Maize (Corn)" in maize.html
