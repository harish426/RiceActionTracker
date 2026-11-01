# Running locally

## 1. Install

Requires Python 3.11+.

**Windows (Command Prompt, no `make`):**

```bat
python -m venv .venv
.venv\Scripts\pip install -e ".[dev,gcp]"
.venv\Scripts\python -m pytest
copy .env.example .env
```
Everywhere below, read `.venv/bin/tracker` as `.venv\Scripts\tracker` (or run
`.venv\Scripts\activate` once, then just `tracker ...`). `make test` = `python -m pytest`.

**Mac/Linux:**

```bash
make setup
```

This creates `.venv/` and installs the app plus test tools. (Manual equivalent:
`python3 -m venv .venv && .venv/bin/pip install -e '.[dev,gcp]'`.)

## 2. Configure

```bash
cp .env.example .env
```

Every value is optional. With nothing set: alerts print in the terminal and keyword matching is
used. Fill in the pieces below as you go.

### Telegram (recommended - instant phone alerts)

1. In Telegram, message **@BotFather** → `/newbot` → follow prompts → copy the **token**.
2. Open a chat with your new bot and send it any message (e.g. "hi").
3. Visit `https://api.telegram.org/bot<TOKEN>/getUpdates` in a browser; find `"chat":{"id": 123456789`.
4. Put both in `.env`: `TELEGRAM_BOT_TOKEN=...` and `TELEGRAM_CHAT_ID=123456789`.

### Email (Gmail example)

1. Enable 2-Step Verification on your Google account, then create an **App Password**
   (Google Account → Security → App passwords).
2. In `.env`:
   ```
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USER=you@gmail.com
   SMTP_PASSWORD=<app password>
   EMAIL_FROM=you@gmail.com
   EMAIL_TO=you@gmail.com
   ```

### Claude API key (recommended - accurate classification)

Create a key at console.anthropic.com and set `ANTHROPIC_API_KEY=...`. Cost is tiny: only *new*
items that pass the keyword prefilter are sent.

### Choose commodities

`COMMODITIES=rice,maize` (default). Each alert carries its commodity: subject `[MAIZE] Auction: …`
with a 🌽 header, or `[RICE] Tender: …` with 🌾. Wheat and other grains are ignored. Use
`COMMODITIES=maize` to track only maize.

### Verify notifications

```bash
.venv/bin/tracker test-notify
```

## 3. Choose websites

Edit `config/sources.yaml` or add via CLI:

```bash
.venv/bin/tracker test-source "https://example.gov.in/notices"      # look first
.venv/bin/tracker add-source "https://example.gov.in/notices" --name "Kerala Supplyco" --state Kerala --tier 2
```

`test-source` prints every link it found, flags those that look like rice auctions, and tells you
whether plain HTTP worked. Tips:

- **Page shows few/no links?** It's probably JavaScript-rendered. Enable the browser:
  `pip install -e '.[browser]' && .venv/bin/playwright install chromium`, set
  `BROWSER_ENABLED=true`, or set `fetch_mode: browser` on that source.
- **SSL errors on a .gov.in site?** Set `verify_ssl: false` on that source only.
- **Quote YAML values** like `id: "off"` / `name: "No"`: bare `off`/`no`/`yes` become booleans.
- Tiers: 1 = most important (FCI, checked every 15 min in cloud), 2 = hourly, 3 = every 6 h.

## 4. Run

```bash
.venv/bin/tracker run                 # all enabled sources
.venv/bin/tracker run --tier 1        # one tier
.venv/bin/tracker run --source fci-home
```

**First run per source is a baseline**: everything currently on the page is remembered and no
alerts are sent. After that, only *new* items trigger alerts. To see alerts for what's already
posted, use `--alert-existing` (once, for a source you just added).

Data lives in `data/tracker.db` (SQLite) and raw pages in `data/snapshots/`. Delete `data/` to
start from scratch.

### Poll continuously on your laptop (optional)

```bash
while true; do .venv/bin/tracker run --tier 1; sleep 900; done
```

### With Docker

```bash
docker compose build
docker compose run --rm tracker run --tier 1
```

## 5. Check health

```bash
.venv/bin/tracker health
```

You also get a Telegram/email message if a site fails repeatedly (default 3 times in a row), if
its item count suddenly collapses (layout change), and when it recovers.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `FAIL ... SSL` | `verify_ssl: false` for that source |
| `0 items` on a page with content | JS-rendered → enable browser |
| No alert for an auction you saw | Run `tracker test-source <url>`; see if it's listed and flagged. Without an API key only items mentioning both an auction term and rice are flagged |
| Telegram `HTTP 400 chat not found` | Send your bot a message first, recheck chat id |
| Wheat/other grain alerts appear | Shouldn't - report the title; with an API key the AI filters by commodity |
| Alert shows "(keyword match - please verify)" | No/failed LLM; set `ANTHROPIC_API_KEY` |
