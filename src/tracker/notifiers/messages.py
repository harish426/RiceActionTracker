"""Render alerts / health events into Messages (plain text + limited HTML)."""

from __future__ import annotations

from html import escape

from tracker.models import Alert, Message, SourceState


def format_alert(alert: Alert) -> Message:
    rows = [("State", alert.state), ("Location", alert.location),
            ("Auction date", alert.auction_date), ("Quantity", alert.quantity),
            ("Reserve price", alert.reserve_price),
            ("Register by", alert.registration_deadline)]
    rows = [(k, v) for k, v in rows if v]
    note = "" if alert.method == "llm" else " (keyword match - please verify)"
    text_lines = [f"RICE AUCTION: {alert.title}{note}"]
    html_lines = [f"<b>🌾 Rice auction:</b> {escape(alert.title)}{escape(note)}"]
    for k, v in rows:
        text_lines.append(f"{k}: {v}")
        html_lines.append(f"<b>{escape(k)}:</b> {escape(v)}")
    if alert.summary:
        text_lines.append(alert.summary)
        html_lines.append(escape(alert.summary))
    text_lines.append("Sources: " + ", ".join(alert.source_names))
    for i, url in enumerate(alert.urls, 1):
        text_lines.append(f"Link {i}: {url}")
        html_lines.append(f'<a href="{escape(url, quote=True)}">Open notice {i}</a>')
    return Message(subject=f"Rice auction: {alert.title[:90]}", text="\n".join(text_lines),
                   html="\n".join(html_lines))


def format_health(source_name: str, problem: str, recovered: bool = False) -> Message:
    icon = "✅" if recovered else "⚠️"
    head = "Source recovered" if recovered else "Source problem"
    return Message(
        subject=f"{head}: {source_name}",
        text=f"{head}: {source_name}\n{problem}",
        html=f"<b>{icon} {head}:</b> {escape(source_name)}\n{escape(problem)}",
    )


def format_digest(states: list[SourceState], names: dict[str, str], alert_count: int) -> Message:
    ok = [s for s in states if s.consecutive_failures == 0 and s.last_success]
    bad = [s for s in states if s.consecutive_failures > 0]
    lines = [f"Weekly digest: {len(ok)}/{len(states)} sources healthy, "
             f"{alert_count} auction alerts recorded."]
    for s in bad:
        lines.append(f"- {names.get(s.source_id, s.source_id)}: failing x{s.consecutive_failures} "
                     f"({s.last_error})")
    text = "\n".join(lines)
    return Message(subject="Rice tracker weekly digest", text=text,
                   html="<b>📊 Weekly digest</b>\n" + escape("\n".join(lines)))
