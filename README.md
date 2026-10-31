# Rice Auction Tracker

Watches Indian government websites (FCI, state civil-supplies departments, …) for **rice auction
(OMSS / e-auction) notices** and alerts you on **Telegram** and **email** the moment a new one
appears. Runs on your laptop for testing and on Google Cloud (Cloud Run Jobs + Scheduler) for
24×7 tracking. Same code, same config files.

## How it works

```
fetch (HTTP → browser fallback → PDF text) → extract links/rows → diff vs. last run
   → keyword prefilter → Claude classifies + extracts fields → dedupe → Telegram + email
```

No per-site scrapers: every link and table row on a page is a candidate, so any website
technology works. Details in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Quick start (5 minutes, no accounts needed)

```bash
make setup                 # creates .venv and installs everything
cp .env.example .env       # optional: add Telegram / email / Anthropic key later
make test                  # 83 offline tests, should all pass
.venv/bin/tracker test-source https://fci.gov.in/   # see what the tracker sees on a page
.venv/bin/tracker run                               # one tracking pass (alerts print to terminal)
```

## Documentation

| Doc | What's in it |
|---|---|
| [docs/LOCAL.md](docs/LOCAL.md) | Run, configure Telegram/email, add websites, daily local use |
| [docs/DEPLOY_GCP.md](docs/DEPLOY_GCP.md) | Deploy to Google Cloud step by step, costs, operations |
| [docs/TESTING.md](docs/TESTING.md) | Running tests, what each test file covers, how to add tests |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Design, module map, why each tool was chosen |

## Commands

| Command | Purpose |
|---|---|
| `tracker run [--tier N] [--source ID] [--alert-existing]` | Check sources and alert on new notices |
| `tracker test-source URL` | Dry run on one URL: shows candidates and rice-auction hits; sends/saves nothing |
| `tracker list-sources` / `add-source URL --name ...` | Manage `config/sources.yaml` |
| `tracker health` | Per-source status |
| `tracker test-notify` | Send a test message to Telegram/email |
| `tracker digest` | Weekly health summary |

## Honest limitations

- URLs in `config/sources.yaml` are starting points; the build environment could not reach the
  real sites, so **verify each with `tracker test-source`** before relying on it.
- Government sites publish no push feed, so "real-time" means polling every 15 min (tier 1).
- Scanned (image-only) PDFs are not read yet (OCR is a planned extension).
- Without `ANTHROPIC_API_KEY` the tracker falls back to keyword matching, which is less accurate.
