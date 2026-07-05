# Deployment guide — Mac mini / Chromebox serving host

## Prerequisites

- Python 3.11+ (3.14 tested locally)
- Network access to configured web catalogs
- Optional: Facebook session cookies for FB-only markets

## One-command setup

```bash
cd /path/to/lobster-price-monitor
bash scripts/install.sh
```

Creates `.venv` and installs `requirements.txt`.

## Dry-run scrape (no Telegram)

```bash
bash scripts/dry_run.sh
```

Equivalent to:

```bash
.venv/bin/python scripts/scrape_markets.py --no-alerts
.venv/bin/python scripts/board.py --html
```

**Alerts are off by default.** To enable Telegram during a scrape:

```bash
.venv/bin/python scripts/scrape_markets.py --alerts
```

Requires `~/.openclaw/secrets/telegram/herb.token`.

## Serve the board

```bash
make serve
# or: .venv/bin/python scripts/serve_board.py --port 8765 --host 0.0.0.0
```

- Local: `http://127.0.0.1:8765/board.html`
- LAN: printed on startup (binds `0.0.0.0` by default)
- Only `board.html` is served; JSONL data files return 403

## Health / readiness

```bash
.venv/bin/python scripts/health_check.py
# Append JSON snapshot to logs/health.jsonl:
.venv/bin/python scripts/health_check.py --log
```

Reports latest run timestamp, per-market coverage, passed/quarantined counts, blocked markets with reasons, and whether alerts were enabled on the last run.

## AAA gate verification

```bash
.venv/bin/python scripts/verify_aaa_gate.py
```

Fails if demo data appears in production mode, provenance is missing, any market lacks live data or a blocker reason, alerts were enabled during dry-run verification, fixture tests fail, or the latest scrape is stale (>36h).

## Logs

Scrape logs append under `logs/scrape-YYYY-MM-DD.log` (git-ignored).

Runtime data lives in `data/` (git-ignored): `prices.jsonl`, `quarantine.jsonl`, `run-log.jsonl`, `market-coverage.json`, `board.html`.

## Secrets / cookies

| Secret | Path | Purpose |
|---|---|---|
| Telegram bot token | `~/.openclaw/secrets/telegram/herb.token` | Price-drop alerts (`--alerts` only) |
| Telegram chat ID | `~/.openclaw/secrets/telegram/chat_id` or env `LOBSTER_TELEGRAM_CHAT_ID` | Alert destination |
| Facebook cookies | `~/.openclaw/secrets/facebook-cookies.json` | Unlock FB-only markets |
| Google CSE | env / `google_cse.py` config | Search fallback before DDG |

Without FB cookies, six markets remain blocked (DDG captcha-prone). The board still serves real prices from web catalogs and marks blocked markets in **SOURCE COVERAGE**.

## Scheduling

Set `LOBSTER_ROOT` to your install path (e.g. `/opt/lobster-price-monitor` on Linux or `/Users/you/lobster-price-monitor` on macOS). Canonical unit files:

| Platform | Scrape | Serve |
|----------|--------|-------|
| Linux systemd | `deploy/systemd/lobster-price-monitor-scrape.service` + `.timer` | `deploy/systemd/lobster-price-monitor-serve.service` |
| macOS launchd | `deploy/launchd/com.erik.lobster-price-monitor.scrape.plist` | `deploy/launchd/com.erik.lobster-price-monitor.serve.plist` |
| cron | `deploy/crontab.example` | run serve via systemd/launchd or `@reboot` |

Replace `LOBSTER_ROOT` placeholders in plist files before `launchctl load`. Root-level `deploy/*.service` and `deploy/*.plist` are pointers to the canonical copies above.

### macOS launchd (example)

Save as `~/Library/LaunchAgents/com.erik.lobster-monitor.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.erik.lobster-monitor</string>
  <key>ProgramArguments</key>
  <array>
    <string>/path/to/lobster-price-monitor/.venv/bin/python</string>
    <string>/path/to/lobster-price-monitor/scripts/scrape_markets.py</string>
    <string>--no-alerts</string>
  </array>
  <key>StartCalendarInterval</key>
  <array>
    <dict><key>Hour</key><integer>7</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Hour</key><integer>11</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Hour</key><integer>15</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Hour</key><integer>19</integer><key>Minute</key><integer>0</integer></dict>
  </array>
  <key>WorkingDirectory</key><string>/path/to/lobster-price-monitor</string>
</dict>
</plist>
```

Load: `launchctl load ~/Library/LaunchAgents/com.erik.lobster-monitor.plist`

### Linux systemd (Chromebox)

```ini
[Unit]
Description=Lobster price monitor scrape
After=network-online.target

[Service]
Type=oneshot
WorkingDirectory=/path/to/lobster-price-monitor
ExecStart=/path/to/lobster-price-monitor/.venv/bin/python scripts/scrape_markets.py --no-alerts
User=erik

[Install]
WantedBy=multi-user.target
```

Pair with a separate `serve_board.py` unit or reverse proxy if you want always-on HTTP.

### cron

```cron
0 7,11,15,19 * * * cd /path/to/lobster-price-monitor && .venv/bin/python scripts/scrape_markets.py --no-alerts
```

## Current market reality (July 2026)

| Market | Status | Notes |
|---|---|---|
| Pine Tree Seafood & Produce | **Live** | WooCommerce web catalog |
| Harbor Fish Market (Lobster) | **Live** | Web catalog; lobster shown as per-lb **range** |
| Harbor Fish Market (Oysters) | **Live** | Web catalog |
| Ancient Mariner | Blocked/Live | FB-only; needs cookies |
| Two Tides Seafood | Blocked/Live | FB-only; needs cookies |
| Scarborough Fish & Lobster | Blocked/Live | FB-only; needs cookies |
| Free Range Fish & Lobster | Blocked/Live | FB-only; needs cookies |
| SoPo Seafood | Blocked/Live | FB-only; needs cookies |
| Five Islands Lobster Co. | Blocked/Live | FB-only; reference menu URL only; manual option |

Partial boards are valid for serving when blocked markets are labeled in SOURCE COVERAGE — never backfilled with fake prices.

## Manual Price Imports

For markets without online structured price lists (like Five Islands Lobster Co.), you can manually import price observations using `scripts/manual_import.py`. This appends a validated row to `prices.jsonl` with `source="manual"` and automatically regenerates `board.html`.

Run it from the root directory:

```bash
# Import a soft shell price of $14.99/lb for Five Islands
.venv/bin/python scripts/manual_import.py --market "Five Islands Lobster Co." --tier "soft_shell" --price 14.99 --unit "lb" --kind "lobster_tier"

# Import a special
.venv/bin/python scripts/manual_import.py --market "Five Islands Lobster Co." --tier "lobster_roll" --price 29.99 --unit "ea" --kind "special"
```

## Enabling Live Telegram Alerts

To enable live Telegram alerts on schedule:
1. Save the Telegram bot token to `~/.openclaw/secrets/telegram/herb.token`.
2. Add the `--alerts` flag to the scrape command in your launchd plist or systemd service file:
   ```bash
   .venv/bin/python scripts/scrape_markets.py --alerts
   ```
3. Reload the launchd agent/systemd service.

To test alert sending and layout without performing a full scrape run, execute:
```bash
.venv/bin/python scripts/test_alert_send.py
```
