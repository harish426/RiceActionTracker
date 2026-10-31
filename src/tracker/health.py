"""Health evaluation: decide when a source problem deserves an alert."""

from __future__ import annotations

from tracker.models import SourceState, utcnow


def record_failure(state: SourceState, error: str, threshold: int) -> str | None:
    """Update state after a failed fetch. Returns a problem text if an alert should fire."""
    state.last_attempt = utcnow()
    state.consecutive_failures += 1
    state.last_error = error[:300]
    if state.consecutive_failures >= threshold and not state.health_alerted:
        state.health_alerted = True
        return f"Failed {state.consecutive_failures} times in a row. Last error: {state.last_error}"
    return None


def record_success(state: SourceState, item_count: int) -> tuple[str | None, bool]:
    """Update state after a good fetch.

    Returns (problem, recovered): `problem` if the page suddenly looks broken
    (items vanished - likely a layout change), `recovered` if a previously
    alerted source is healthy again.
    """
    now = utcnow()
    prev_count = state.last_item_count
    recovered = state.health_alerted and state.consecutive_failures > 0
    state.last_attempt = now
    state.last_success = now
    state.consecutive_failures = 0
    state.last_error = None

    problem = None
    suspicious = state.baselined and prev_count >= 5 and item_count < prev_count * 0.3
    if not suspicious:  # keep the 'expected' count while the page looks broken
        state.last_item_count = item_count
    if suspicious and not state.health_alerted:
        state.health_alerted = True
        problem = (f"Item count dropped from {prev_count} to {item_count}. "
                   "The site layout may have changed.")
        recovered = False
    elif recovered or (state.health_alerted and not suspicious):
        state.health_alerted = False
        recovered = True
    return problem, recovered
