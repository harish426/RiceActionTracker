"""Orchestration: fetch -> extract -> diff -> classify -> dedupe -> notify."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from tracker import health
from tracker.classify import Classifier, to_alert
from tracker.commodities import commodity_hits, is_action_like
from tracker.config import Settings
from tracker.extract import extract_candidates
from tracker.fetchers.base import Fetcher, FetchError
from tracker.models import Alert, Candidate, Source, utcnow
from tracker.notifiers.base import Notifier, NotifyError
from tracker.notifiers.messages import format_alert, format_health
from tracker.snapshots import SnapshotStore
from tracker.storage.base import Storage

log = logging.getLogger(__name__)


@dataclass
class Deps:
    settings: Settings
    storage: Storage
    fetcher: Fetcher
    classifier: Classifier
    notifier: Notifier
    snapshots: SnapshotStore


@dataclass
class SourceReport:
    source_id: str
    ok: bool = True
    error: str | None = None
    items: int = 0
    new_items: int = 0
    baseline: bool = False
    alerts: int = 0


@dataclass
class RunReport:
    sources: list[SourceReport] = field(default_factory=list)
    retried_alerts: int = 0

    @property
    def failed(self) -> list[SourceReport]:
        return [r for r in self.sources if not r.ok]

    @property
    def alerts(self) -> int:
        return sum(r.alerts for r in self.sources)


def _safe_send(deps: Deps, message) -> bool:
    try:
        deps.notifier.send(message)
        return True
    except NotifyError as exc:
        log.error("notification failed: %s", exc)
        return False


def deliver_alert(deps: Deps, alert: Alert) -> bool:
    """Send an alert and persist whether it was delivered (so failures are retried)."""
    alert.notified = _safe_send(deps, format_alert(alert))
    deps.storage.save_alert(alert)
    return alert.notified


def retry_pending(deps: Deps) -> int:
    sent = 0
    for alert in deps.storage.pending_alerts():
        if deliver_alert(deps, alert):
            sent += 1
    return sent


def _classify_new(deps: Deps, source: Source, cand: Candidate, pdf_budget: list[int]):
    """Prefilter, optionally peek inside vague PDF links, then classify."""
    text = cand.text
    extra = ""
    keys = deps.settings.commodity_keys
    if cand.is_pdf and not (is_action_like(text) and commodity_hits(text, keys)) and pdf_budget[0] > 0:
        pdf_budget[0] -= 1
        try:
            extra = deps.fetcher.fetch_pdf_text(cand.url, source.verify_ssl)[:4000]
        except FetchError:
            extra = ""
    if not is_action_like(f"{text} {extra}"):
        return None
    result = deps.classifier.classify(cand, extra)
    return result if result.is_relevant else None


def process_source(deps: Deps, source: Source, alert_existing: bool = False) -> SourceReport:
    report = SourceReport(source.id)
    storage = deps.storage
    state = storage.get_state(source.id)

    try:
        fetched = deps.fetcher.fetch(source)
        candidates = extract_candidates(fetched.text, fetched.final_url, source.id) \
            if not fetched.is_pdf else [Candidate(title=source.name + " (PDF)", url=source.url,
                                                  context=fetched.text[:500], source_id=source.id)]
    except FetchError as exc:
        report.ok, report.error = False, str(exc)
        problem = health.record_failure(state, str(exc), deps.settings.failure_alert_threshold)
        storage.save_state(state)
        if problem:
            _safe_send(deps, format_health(source.name, problem))
        return report

    report.items = len(candidates)
    problem, recovered = health.record_success(state, len(candidates))
    seen = storage.seen_fingerprints(source.id)
    new = [c for c in candidates if c.fingerprint not in seen]
    report.new_items = len(new)

    if candidates and not state.baselined:
        # First successful run: remember everything; only alert if explicitly asked.
        state.baselined = True
        report.baseline = True
        to_check = new if alert_existing else []
    else:
        to_check = new

    pdf_budget = [deps.settings.pdf_lookup_limit]
    for cand in to_check:
        result = _classify_new(deps, source, cand, pdf_budget)
        if not result:
            continue
        alert = to_alert(result, cand, source.name, source.state)
        existing = storage.get_alert(alert.key)
        if existing:  # same auction seen on another site: just attach the extra link
            changed = False
            if cand.url not in existing.urls:
                existing.urls.append(cand.url)
                changed = True
            if source.name not in existing.source_names:
                existing.source_names.append(source.name)
                changed = True
            if changed:
                storage.save_alert(existing)
            continue
        report.alerts += 1
        deliver_alert(deps, alert)

    if new:
        storage.add_seen(source.id, new)
        state.last_change = utcnow()
        if fetched.text:
            deps.snapshots.save(source.id, fetched.text)
    storage.save_state(state)

    if problem:
        _safe_send(deps, format_health(source.name, problem))
    elif recovered:
        _safe_send(deps, format_health(source.name, "Working normally again.", recovered=True))
    return report


def run_sources(deps: Deps, sources: list[Source], alert_existing: bool = False) -> RunReport:
    run = RunReport()
    run.retried_alerts = retry_pending(deps)

    def work(src: Source) -> SourceReport:
        try:
            return process_source(deps, src, alert_existing)
        except Exception as exc:  # one bad source must never stop the others
            log.exception("unexpected error in %s", src.id)
            return SourceReport(src.id, ok=False, error=f"{type(exc).__name__}: {exc}")

    workers = max(1, deps.settings.max_workers)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        run.sources = list(pool.map(work, sources))
    return run
