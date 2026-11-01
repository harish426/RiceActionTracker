"""Command line: `tracker --help`."""

from __future__ import annotations

import logging
import re
from pathlib import Path

import typer

from tracker.classify import build_classifier
from tracker.config import Settings, load_sources
from tracker.extract import extract_candidates
from tracker.fetchers import HttpFetcher, LadderFetcher
from tracker.fetchers.throttle import HostThrottle
from tracker.models import Message, Source
from tracker.notifiers import build_notifier
from tracker.notifiers.messages import format_digest
from tracker.pipeline import Deps, run_sources
from tracker.snapshots import build_snapshots
from tracker.storage import build_storage

app = typer.Typer(help="Rice auction notice tracker", no_args_is_help=True)


def _fetcher(settings: Settings):
    http = HttpFetcher(settings.user_agent, settings.request_timeout,
                       HostThrottle(settings.host_min_interval))
    browser = None
    if settings.browser_enabled:
        from tracker.fetchers.browser import BrowserFetcher

        browser = BrowserFetcher(settings.user_agent)
    return LadderFetcher(http, browser)


def build_deps(settings: Settings) -> Deps:
    return Deps(settings=settings, storage=build_storage(settings), fetcher=_fetcher(settings),
                classifier=build_classifier(settings.anthropic_api_key, settings.llm_model),
                notifier=build_notifier(settings), snapshots=build_snapshots(settings))


@app.callback()
def main(verbose: bool = typer.Option(False, "--verbose", "-v")) -> None:
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@app.command()
def run(
    tier: int = typer.Option(None, help="Only sources of this tier (1, 2, 3)"),
    source: str = typer.Option(None, help="Only this source id"),
    alert_existing: bool = typer.Option(False, help="On a source's first run, alert on items "
                                        "already on the page instead of just baselining"),
    fail_on_error: bool = typer.Option(False, help="Exit 1 if any source failed"),
) -> None:
    """Check sources, alert on new rice auction notices."""
    settings = Settings()
    sources = [s for s in load_sources(settings.sources_file) if s.enabled]
    if tier is not None:
        sources = [s for s in sources if s.tier == tier]
    if source:
        sources = [s for s in sources if s.id == source]
    if not sources:
        typer.echo("No matching enabled sources.")
        raise typer.Exit(1)
    report = run_sources(build_deps(settings), sources, alert_existing)
    for r in report.sources:
        status = "OK  " if r.ok else "FAIL"
        extra = " (baseline)" if r.baseline else ""
        typer.echo(f"{status} {r.source_id}: {r.items} items, {r.new_items} new, "
                   f"{r.alerts} alerts{extra}" + (f" - {r.error}" if r.error else ""))
    typer.echo(f"Done: {len(sources)} sources, {report.alerts} new alerts, "
               f"{len(report.failed)} failed, {report.retried_alerts} retried alerts sent.")
    if fail_on_error and report.failed:
        raise typer.Exit(1)


@app.command("test-source")
def test_source(url: str, verify_ssl: bool = True, limit: int = 40,
                browser: bool = typer.Option(False, help="Render with a headless browser (JS sites)"),
                save_html: str = typer.Option(None, help="Write the fetched HTML to this file")) -> None:
    """Fetch one URL and show what the tracker would see. Changes nothing, sends nothing."""
    settings = Settings()
    if browser:
        settings.browser_enabled = True
    src = Source(id="adhoc", name="adhoc", url=url, verify_ssl=verify_ssl,
                 fetch_mode="browser" if browser else "auto")
    fetched = _fetcher(settings).fetch(src)
    if save_html:
        Path(save_html).write_text(fetched.text, encoding="utf-8")
    cands = extract_candidates(fetched.text, fetched.final_url, "adhoc")
    classifier = build_classifier(settings.anthropic_api_key, settings.llm_model)
    from tracker.classify import is_auction_like

    typer.echo(f"Fetched via {fetched.used}, HTTP {fetched.status}, {len(cands)} candidates "
               f"(classifier: {type(classifier).__name__})\n")
    hits = 0
    for c in cands:
        if is_auction_like(c.text):
            res = classifier.classify(c)
            mark = "RICE-AUCTION" if res.is_rice_auction else "auction-ish "
            hits += res.is_rice_auction
            typer.echo(f"[{mark}] {c.title[:90]}\n    {c.url}")
    typer.echo(f"\nShowing first {limit} of {len(cands)} candidates:")
    for c in cands[:limit]:
        typer.echo(f"  - {c.title[:90]}")
    typer.echo(f"\n{hits} rice-auction-like items.")


@app.command("list-sources")
def list_sources() -> None:
    """List configured sources."""
    for s in load_sources(Settings().sources_file):
        flag = "on " if s.enabled else "off"
        typer.echo(f"[{flag}] tier{s.tier} {s.id:<28} {s.url}")


@app.command("add-source")
def add_source(url: str, name: str = typer.Option(...), state: str = typer.Option(None),
               tier: int = 2, source_id: str = typer.Option(None, "--id")) -> None:
    """Append a new website to config/sources.yaml."""
    settings = Settings()
    sid = source_id or re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if any(s.id == sid for s in load_sources(settings.sources_file)):
        typer.echo(f"Source id '{sid}' already exists.")
        raise typer.Exit(1)
    block = f"\n  - id: \"{sid}\"\n    name: \"{name}\"\n    url: \"{url}\"\n"
    if state:
        block += f"    state: \"{state}\"\n"
    block += f"    tier: {tier}\n"
    path = Path(settings.sources_file)
    path.write_text(path.read_text(encoding="utf-8").rstrip("\n") + "\n" + block, encoding="utf-8")
    typer.echo(f"Added {sid}. Try: tracker test-source {url}")


@app.command()
def health() -> None:
    """Show per-source health."""
    settings = Settings()
    storage = build_storage(settings)
    names = {s.id: s.name for s in load_sources(settings.sources_file)}
    for st in storage.list_states():
        label = names.get(st.source_id, st.source_id)
        ok = "OK  " if st.consecutive_failures == 0 else "FAIL"
        if st.last_success:
            typer.echo(f"{ok} {label:<40} items={st.last_item_count:<4} "
                       f"last_ok={st.last_success:%Y-%m-%d %H:%M}")
        else:
            typer.echo(f"{ok} {label:<40} never succeeded - {st.last_error}")


@app.command()
def digest() -> None:
    """Send the weekly health digest (schedule this weekly in the cloud)."""
    settings = Settings()
    storage = build_storage(settings)
    names = {s.id: s.name for s in load_sources(settings.sources_file)}
    msg = format_digest(storage.list_states(), names, len(storage.recent_alerts(1000)))
    build_notifier(settings).send(msg)
    typer.echo("Digest sent.")


@app.command("test-notify")
def test_notify() -> None:
    """Send a test message through every configured channel (Telegram / email)."""
    settings = Settings()
    build_notifier(settings).send(Message(
        subject="Rice tracker test", text="Test message from Rice Auction Tracker. It works!",
        html="<b>✅ Rice Auction Tracker</b>\nTest message - notifications work."))
    typer.echo("Sent.")


if __name__ == "__main__":
    app()
