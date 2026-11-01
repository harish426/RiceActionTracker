# Architecture

## Flow

```
Cloud Scheduler (tier cron) ─▶ Cloud Run Job: `tracker run --tier N`
   for each source (thread pool, per-host throttle):
     1 FETCH     LadderFetcher: HTTP → (if page looks JS-rendered) Playwright; PDFs → text
     2 EXTRACT   every <a>, linkless table row, or (fallback) whole-page hash → Candidate
     3 DIFF      fingerprint(url+title) vs. `seen` store → new candidates only
     4 FILTER    cheap keyword prefilter (auction/sale/tender words, EN + Hindi/Telugu/…)
     5 CLASSIFY  Claude forced tool-call → relevant? + commodity (rice|maize|other) + type + fields;
                 keyword fallback (needs action word AND commodity word, word-boundary matched)
     6 DEDUPE    alert key = commodity|state|date|quantity → same auction on 2 sites = 1 alert
     7 NOTIFY    Telegram + email; failures stay "pending" and retry next run
   health: consecutive failures / item-count collapse / recovery → messages
```

First successful run of a source only **baselines** (stores what's there) so you aren't flooded.

## Module map (`src/tracker/`)

| Module | Responsibility |
|---|---|
| `models.py` | Pydantic models: Source, Candidate, Classification, Alert, SourceState, Message |
| `config.py` | `Settings` (env/.env) and `sources.yaml` loader |
| `fetchers/` | `http.py` (httpx+tenacity), `browser.py` (Playwright, optional), `pdf.py`, `ladder.py`, `throttle.py` |
| `extract.py` | HTML → candidates, site-agnostic |
| `commodities.py` | commodity definitions (rice, maize), multilingual term lists, word-boundary matching |
| `classify.py` | keyword & LLM classifiers, alert keys |
| `storage/` | `sqlite.py` (local), `firestore.py` (cloud), same `Storage` protocol |
| `snapshots.py` | raw page archive: local folder or GCS |
| `notifiers/` | telegram, email, console, multi fan-out, message formatting |
| `health.py` | pure functions deciding when to alert about a source |
| `pipeline.py` | orchestration |
| `cli.py` | Typer commands |

**Local/cloud parity**: only `STORAGE_BACKEND`, `SNAPSHOT_BACKEND` and where secrets come from
differ. Everything else, including tests, is identical.

## Why each tool

| Tool | Reason |
|---|---|
| Python 3.11+ | Best scraping/PDF/LLM ecosystem |
| httpx + tenacity | Fast, timeouts, redirects, retry/backoff on 5xx/429 for flaky .gov.in servers |
| selectolax (lexbor) | Fast, forgiving HTML parser for broken government markup |
| Playwright (optional) | Only for JS-rendered portals; heavy so it's a fallback |
| pypdf | Many notices are text PDFs; link text is often just "Click here" so we peek inside |
| Claude (tool-use) | Language- and layout-agnostic judgement incl. Hindi; forced tool schema gives validated JSON |
| pydantic / pydantic-settings | Validated config & models |
| Typer | CLI that doubles as the Cloud Run Job entrypoint |
| SQLite → Firestore | Zero-setup local; serverless, free-tier cloud |
| Cloud Run Jobs + Scheduler | Run-to-completion containers, billed per second, no servers |
| Secret Manager | Tokens never in image or env files |
| Telegram + SMTP | Instant free push + durable email record |

## Risks

- **Cloud IP blocking / CAPTCHAs**: government sites may refuse data-centre IPs. Mitigations:
  Mumbai region, polite rate limit, browser mode; worst case route through a proxy or watch an
  alternative source (RSS, a state's PDF listing).
- **Silent breakage**: guarded by health alerts and the weekly digest.
- **Scanned PDFs**: not OCR'd yet.
- **Politeness**: ≥2 s between hits to the same host; tier 1 = 15 min is the fastest cadence.
