# Deployment guide — Mac mini / Chromebox serving host

> **Production host agent:** See **[NEXT_AGENT.md](NEXT_AGENT.md)** for the phased install → scheduler → ops promotion runbook.

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

## Host deploy orchestrator (Gate D Wave 5)

Unified entry point for production-host agents:

```bash
bash scripts/deploy_host.sh --dry-run --phase all          # preview phases 1–2
bash scripts/deploy_host.sh --dry-run --phase all --promote # preview all phases
make deploy-host                                            # run phases 1–2
make deploy-host -- --promote                               # run phases 1–2–3 (live alerts)
```

| Phase | Script / target | Gate checkpoint |
|-------|-----------------|-----------------|
| 1 | `make bootstrap-host` | health + CI-safe verify gates |
| 2 | `make install-scheduler` | `make verify-deploy` |
| 3 | `make promote-ops` (opt-in) | `make verify-ops` |

**Rollback:** `make demote-ops` swaps ops scheduler back to dry-run and runs `make verify-deploy`.

**Secrets preflight:** `bash scripts/preflight_secrets.sh` (add `--require-telegram` before ops promotion).

## Dry-run scrape (no Telegram)

```bash
bash scripts/dry_run.sh
```

Equivalent to:

```bash
.venv/bin/python scripts/scrape_markets.py --no-alerts
```

(`scrape_markets.py` regenerates `data/board.html` at the end of each run.)

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

Set `LOBSTER_ROOT` to your install path (e.g. `/opt/lobster-price-monitor` on Linux or `/Users/you/lobster-price-monitor` on macOS). Canonical unit templates use the `LOBSTER_ROOT` placeholder on **both** macOS and Linux — substitute at install time (see `scripts/install_scheduler.sh`).

| Platform | Scrape | Scrape (ops / alerts) | Serve | Health log |
|----------|--------|----------------------|-------|------------|
| Linux systemd | `deploy/systemd/lobster-price-monitor-scrape.service` + `.timer` | `deploy/systemd/lobster-price-monitor-scrape.ops.service` + `.ops.timer` | `deploy/systemd/lobster-price-monitor-serve.service` | `lobster-price-monitor-health.service` + `.timer` |
| macOS launchd | `deploy/launchd/com.erik.lobster-price-monitor.scrape.plist` (Label: `…scrape`) | `deploy/launchd/com.erik.lobster-price-monitor.scrape.ops.plist` (Label: `…scrape.ops`) | `deploy/launchd/com.erik.lobster-price-monitor.serve.plist` | `com.erik.lobster-price-monitor.health.plist` |
| cron | `deploy/crontab.example` (`run_scrape.sh`, no alerts) | `LOBSTER_ALERTS=1` + `run_scrape.sh` (see commented ops block) | run serve via systemd/launchd or `@reboot` | manual or health unit |

**One-command install (recommended):**

```bash
bash scripts/install_scheduler.sh --dry-run   # preview
make install-scheduler                        # install dry-run scrape + serve + health
make verify-deploy                            # host deploy gate
```

Root-level `deploy/*.service` and `deploy/*.plist` are pointers to the canonical copies above.

### macOS launchd

Use the canonical plists in [deploy/launchd/](deploy/launchd/). `install_scheduler.sh` substitutes `LOBSTER_ROOT` and loads agents automatically. Manual fallback:

| Unit | Label | File |
|------|-------|------|
| Dry-run scrape | `com.erik.lobster-price-monitor.scrape` | `com.erik.lobster-price-monitor.scrape.plist` |
| Ops scrape (alerts) | `com.erik.lobster-price-monitor.scrape.ops` | `com.erik.lobster-price-monitor.scrape.ops.plist` |
| Board server | `com.erik.lobster-price-monitor.serve` | `com.erik.lobster-price-monitor.serve.plist` |
| Daily health log | `com.erik.lobster-price-monitor.health` | `com.erik.lobster-price-monitor.health.plist` |

```bash
# Example: dry-run scrape + serve
cp deploy/launchd/com.erik.lobster-price-monitor.scrape.plist ~/Library/LaunchAgents/
cp deploy/launchd/com.erik.lobster-price-monitor.serve.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.erik.lobster-price-monitor.scrape.plist
launchctl load ~/Library/LaunchAgents/com.erik.lobster-price-monitor.serve.plist
```

Gate verifiers expect these exact labels (see `scripts/verify_production_gate.py`).

### Linux systemd (Chromebox)

`install_scheduler.sh` substitutes `LOBSTER_ROOT` into unit templates and installs to `/etc/systemd/system/`. Manual fallback example:

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

## Enabling Live Telegram Alerts (Gate D ops)

Default scrape paths use `--no-alerts`. To promote to live ops alerts:

### One-command promotion (recommended)

```bash
# Preview planned actions without changing the host scheduler
bash scripts/promote_ops.sh --dry-run

# Promote: swap dry-run scheduler → ops, confirm scrape, verify
make promote-ops
# or: bash scripts/promote_ops.sh
```

`promote_ops.sh` will:

1. Verify Telegram token at `~/.openclaw/secrets/telegram/herb.token` and `.venv` exist.
2. **Unload/disable** the dry-run scheduler.
3. **Load/enable** the ops scheduler (`LOBSTER_ALERTS=1`).
4. Run one confirmation scrape with alerts enabled.
5. Run `make verify-ops` (requires ops unit loaded; dry-run must be unloaded).

Set `LOBSTER_ROOT` if the install path differs from the repo root (e.g. `/opt/lobster-price-monitor`).

### Manual promotion (fallback)

1. Save the Telegram bot token to `~/.openclaw/secrets/telegram/herb.token` (and chat ID to `~/.openclaw/secrets/telegram/chat_id` or env `LOBSTER_TELEGRAM_CHAT_ID`).
2. **Unload** the dry-run scheduler:
   - macOS: `launchctl unload ~/Library/LaunchAgents/com.erik.lobster-price-monitor.scrape.plist`
   - Linux: `sudo systemctl disable --now lobster-price-monitor-scrape.timer`
3. **Load** the ops scheduler (labels/units differ from dry-run):
   - macOS: copy `deploy/launchd/com.erik.lobster-price-monitor.scrape.ops.plist` (Label `com.erik.lobster-price-monitor.scrape.ops`), replace `LOBSTER_ROOT`, then `launchctl load …`
   - Linux: enable `lobster-price-monitor-scrape.ops.timer` (pairs with `lobster-price-monitor-scrape.ops.service`)
4. Run one manual scrape to confirm alerts path: `LOBSTER_ALERTS=1 scripts/run_scrape.sh`
5. Verify ops readiness: `make verify-ops` (host) or `make verify-ops-ci` (CI-safe smoke).

`make verify-production` accepts either dry-run or ops scrape scheduler on a promoted host. `make verify-ops` requires the **ops** scheduler loaded and dry-run **unloaded**.

Alternative enable paths (without swapping units):

- Set `LOBSTER_ALERTS=1` (or `LOBSTER_ALERTS=true`) in the scheduler environment — `scripts/run_scrape.sh` picks this up automatically; or
- Pass `--alerts` directly: `.venv/bin/python scripts/scrape_markets.py --alerts`

RALPH Learnings are auto-updated after each scrape (or run manually):

```bash
.venv/bin/python scripts/update_ralph_learnings.py
```

To test alert sending and layout without performing a full scrape run (sends **live** Telegram messages):

```bash
.venv/bin/python scripts/send_test_alert.py
```
