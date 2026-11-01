# Testing

All tests are **offline and fast** (< 1 s): no real websites, no real Telegram/SMTP/Claude/GCP.

```bash
make test                       # everything
.venv/bin/pytest tests/test_pipeline.py -k baseline   # a subset
make lint                       # ruff
make check                      # lint + tests
```

Run `make test` after every change. CI runs the same on every push.

| File | Covers |
|---|---|
| `test_extract.py` | link/row extraction, URL resolving, script/nav removal, page-hash fallback |
| `test_fetchers.py` | HTTP retries/backoff, errors, PDF handling, per-host throttle, JS-page detection, browser fallback ladder |
| `test_classify.py` | keyword prefilter (incl. Hindi/Telugu), rice vs maize detection, word boundaries ('price' ≠ rice), keyword classifier, Claude classifier with a fake client, LLM-failure fallback, cross-site dedupe keys |
| `test_storage.py` | SQLite **and** Firestore adapters run the *same* tests (Firestore uses an in-memory fake) |
| `test_notifiers.py` | message formatting/escaping, Telegram, email (fake SMTP), multi-channel fan-out, factory |
| `test_health.py` | failure thresholds, recovery, layout-change detection |
| `test_pipeline.py` | end-to-end logic: baseline, new-notice alert, no duplicates, wheat/irrelevant ignored, PDF peeking, failed-delivery retry, failure isolation |
| `test_cli.py` | real CLI commands against a mocked website |
| `test_config_snapshots.py` | sources.yaml loading, env settings, snapshot stores |

## Adding a test for a new website's quirks

1. Save the page: `curl -A Mozilla/5.0 https://site/notices > tests/fixtures/site.html`
2. Add a test in `test_extract.py` asserting the expected notice links are found.
3. Add a pipeline test with `FakeFetcher({url: html})` if behavior should differ.

## Pytest helpers (`tests/conftest.py`)

`FakeFetcher` (serves HTML from a dict), `RecordingNotifier` (captures messages), and a `deps`
fixture wiring an in-memory SQLite store: use them to test any new pipeline behavior.
