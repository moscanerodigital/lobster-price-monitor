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

## Host teardown (Gate D Wave 6)

Remove all schedulers from a host (does not delete `.venv`, `data/`, or the repo):

```bash
bash scripts/teardown_host.sh --dry-run       # preview
make teardown-host                             # demote ops if loaded → uninstall all
make teardown-host TEARDOWN_FLAGS=--purge-files  # also delete installed plists/units
make uninstall-scheduler                       # uninstall schedulers only
bash scripts/deploy_host.sh --teardown         # same as teardown-host via orchestrator
bash scripts/deploy_host.sh --teardown --purge-files
```

| Flag | Effect |
|------|--------|
| `--skip-demote` | Uninstall without demoting ops first |
| `--skip-health` | Leave health timer/agent installed |
| `--purge-files` | Delete installed plists/units from disk after unload |

After teardown, `make verify-deploy` is expected to fail (no schedulers loaded). Re-deploy with `make deploy-host`.

## Host upgrade (Gate D Wave 7)

In-place upgrade for hosts that already have `.venv`, `data/`, and schedulers loaded:

```bash
bash scripts/upgrade_host.sh --dry-run       # preview
make upgrade-host                             # pull → install → reload → scrape → verify
bash scripts/deploy_host.sh --upgrade        # same via orchestrator
```

| Step | Action |
|------|--------|
| Pull | `git pull --ff-only` (use `--skip-pull` for non-git installs) |
| Deps | `scripts/install.sh` |
| Reload | Re-copy scheduler units; preserves dry-run vs ops mode |
| Verify | `make verify-deploy` (dry-run) or `make verify-ops` (ops) |

| Flag | Effect |
|------|--------|
| `--skip-pull` | Skip git pull |
| `--skip-scrape` | Skip confirmation scrape |
| `--skip-verify` | Skip gate verification |
| `--skip-health` | Skip health timer reload |

Does not demote ops, promote dry-run, or delete `data/`.

## Host status (Gate D Wave 8)

Read-only operational diagnostics:

```bash
bash scripts/status_host.sh              # human-readable report
bash scripts/status_host.sh --json       # machine-readable JSON
make status-host
bash scripts/deploy_host.sh --status     # same via orchestrator
```

| Section | Content |
|---------|---------|
| Scheduler | Mode (none / dry-run / ops) and unit loaded/active state |
| Code | Git short revision (when `.git` exists) |
| Scrape | Latest `run-log.jsonl` timestamp; warns if >24h stale |
| Health | `health_check.py` report (live/blocked markets, readiness) |
| Serve | Localhost, LAN, and Tailscale tailnet board URLs |
| Secrets | Non-fatal `preflight_secrets.sh` summary |

Exit codes: `0` healthy · `1` degraded · `2` fatal preflight (missing venv, bad `LOBSTER_ROOT`).

## Host watchdog (Gate D Wave 9)

Status-driven Telegram alerts when the host is unhealthy:

```bash
bash scripts/watchdog_host.sh              # check only
bash scripts/watchdog_host.sh --notify     # alert if degraded/fatal
bash scripts/watchdog_host.sh --notify --dry-run  # preview
make watchdog-host
bash scripts/deploy_host.sh --watchdog     # same via orchestrator
```

| Flag | Effect |
|------|--------|
| `--notify` | Send Telegram when exit code > 0 (also enabled by `LOBSTER_WATCHDOG_ALERTS=1`) |
| `--force` | Bypass 6h dedupe window |
| `--dry-run` | Check only; print would-alert without sending |

Watchdog reuses `status_host.sh --json` checks. Deduped alerts log to `alerts_sent.jsonl` with `kind=host_watchdog`.

**Scheduler:** Ops promotion installs a watchdog timer (10:00 and 22:00 local) with `LOBSTER_WATCHDOG_RECOVER=1`, `LOBSTER_WATCHDOG_DEEP_RECOVER=1`, `LOBSTER_WATCHDOG_REDEPLOY_RECOVER=1`, `LOBSTER_WATCHDOG_REBUILD_RECOVER=1`, and `LOBSTER_WATCHDOG_REPROVISION_RECOVER=1` (recover before alert, full recovery ladder on failure). Opt in on dry-run hosts with `bash scripts/install_scheduler.sh --with-watchdog`.

## Closed-loop ops recovery (Gate D Wave 11)

Ops watchdog runs auto-recovery before alerting. `make verify-ops` on a host checks `LOBSTER_WATCHDOG_RECOVER=1` in the watchdog unit. `status_host.sh --json` reports `units.watchdog_recover_enabled`.

To disable auto-recovery on a host, set `LOBSTER_WATCHDOG_RECOVER=0` in the watchdog plist/systemd unit and reload. Existing ops hosts pick up the default on `make upgrade-host`.

## Recovery escalation (Gate D Wave 12)

Tracks consecutive watchdog failures in `data/host-health.jsonl` and escalates after repeated degraded outcomes:

```bash
bash scripts/recover_host.sh --deep              # tier-2 upgrade_host after tier-1
bash scripts/watchdog_host.sh --recover --deep-recover --notify
make status-host                                 # reports watchdog_health failure streak
```

| Setting | Effect |
|---------|--------|
| `LOBSTER_WATCHDOG_DEEP_RECOVER=1` | Run `upgrade_host.sh` when tier-1 recovery leaves host degraded (default on ops watchdog) |
| `LOBSTER_WATCHDOG_ESCALATE_AFTER=3` | Send escalation Telegram after N consecutive failures in 48h |

Escalation alerts (`kind=host_escalation`) include failure streak, recovery notes, and manual steps (`make upgrade-host`, `make redeploy-host`, `make rebuild-host`, `make reprovision-host`, `make recover-host`, `make demote-ops`). Normal watchdog alerts still fire below the threshold.

`make verify-ops` on a host also checks `LOBSTER_WATCHDOG_DEEP_RECOVER=1` in the watchdog unit.

## Scheduler redeploy (Gate D Wave 13)

Tier-3 recovery when tier-1 reload and tier-2 upgrade leave the host degraded:

```bash
bash scripts/redeploy_host.sh --dry-run           # preview
make redeploy-host                                 # uninstall + reinstall schedulers
bash scripts/recover_host.sh --deep --redeploy     # tier-2 then tier-3
bash scripts/deploy_host.sh --redeploy             # same via orchestrator
```

| Setting | Effect |
|---------|--------|
| `LOBSTER_WATCHDOG_REDEPLOY_RECOVER=1` | Run `redeploy_host.sh` when tier-2 leaves host degraded (default on ops watchdog) |

Redeploy preserves `data/`, `.venv/`, and scheduler mode (re-promotes ops when needed). Does not run `git pull`.

`make verify-ops` on a host also checks `LOBSTER_WATCHDOG_REDEPLOY_RECOVER=1` in the watchdog unit.

## Full host rebuild (Gate D Wave 14)

Tier-4 recovery when tier-1 reload, tier-2 upgrade, and tier-3 redeploy leave the host degraded:

```bash
bash scripts/rebuild_host.sh --dry-run            # preview
make rebuild-host                                  # fresh venv + redeploy schedulers
bash scripts/recover_host.sh --deep --redeploy --rebuild  # tier-2/3/4 ladder
bash scripts/deploy_host.sh --rebuild              # same via orchestrator
```

| Setting | Effect |
|---------|--------|
| `LOBSTER_WATCHDOG_REBUILD_RECOVER=1` | Run `rebuild_host.sh` when tier-3 leaves host degraded (default on ops watchdog) |

Rebuild preserves `data/` and scheduler mode (re-promotes ops when needed). Removes and recreates `.venv`, runs bootstrap verify, then redeploys schedulers. Does not run `git pull` or full teardown.

`make verify-ops` on a host also checks `LOBSTER_WATCHDOG_REBUILD_RECOVER=1` in the watchdog unit.

## Full host reprovision (Gate D Wave 15)

Tier-5 recovery when tier-1 reload, tier-2 upgrade, tier-3 redeploy, and tier-4 rebuild leave the host degraded:

```bash
bash scripts/reprovision_host.sh --dry-run            # preview
make reprovision-host                                  # teardown + pull + rebuild + redeploy
bash scripts/recover_host.sh --deep --redeploy --rebuild --reprovision  # tier-2/3/4/5 ladder
bash scripts/deploy_host.sh --reprovision              # same via orchestrator
```

| Setting | Effect |
|---------|--------|
| `LOBSTER_WATCHDOG_REPROVISION_RECOVER=1` | Run `reprovision_host.sh` when tier-4 leaves host degraded (default on ops watchdog) |

Reprovision preserves `data/` and scheduler mode (re-promotes ops when needed). Runs full teardown with `--purge-files`, `git pull`, fresh venv, bootstrap verify, then scheduler redeploy.

When tier-5 reprovision still leaves the host degraded on an ops host, recovery auto-demotes to dry-run (stops live alerts; manual intervention required).

`make verify-ops` on a host also checks `LOBSTER_WATCHDOG_REPROVISION_RECOVER=1` in the watchdog unit.

## Host recovery (Gate D Wave 10)

Status-driven auto-recovery for degraded hosts:

```bash
bash scripts/recover_host.sh              # check + remediate
bash scripts/recover_host.sh --dry-run    # preview actions
bash scripts/recover_host.sh --notify     # Telegram summary of recovery
make recover-host
bash scripts/deploy_host.sh --recover     # same via orchestrator
```

| Flag | Effect |
|------|--------|
| `--dry-run` | Preview actions; always exit 0 |
| `--notify` | Send deduped Telegram summary (requires secrets) |
| `--force` | Bypass 6h recovery-alert dedupe window |
| `--deep` | Enable tier-2 `upgrade_host` when tier-1 leaves host degraded |

Recovery actions (based on `status_host.sh --json`):

| Condition | Action |
|-----------|--------|
| Serve not active | Reload serve unit |
| Scrape stale (>24h) | Run confirmation scrape |
| Scrape scheduler not loaded | Reload scrape scheduler |
| Health not ready | Trigger scrape + re-run health check |
| Ops host missing watchdog | Install watchdog timer |
| Tier-1 insufficient (with `--deep`) | Run `upgrade_host.sh` (refresh deps + reload schedulers) |

Does not auto-fix fatal preflight errors or missing secrets.

**Watchdog integration:** `bash scripts/watchdog_host.sh --recover --notify` runs recovery before re-checking status. Scheduled ops watchdog enables this by default (`LOBSTER_WATCHDOG_RECOVER=1`). Alerts after failed recovery include `auto-recovery attempted`.

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
- LAN: printed on startup (binds `0.0.0.0` by default via `BIND` / `PORT` in the Makefile)
- Only `board.html` is served; JSONL data files return 403

### Tailscale (tailnet)

Production schedulers bind `0.0.0.0:8765` (`deploy/launchd/com.erik.lobster-price-monitor.serve.plist` and `deploy/systemd/lobster-price-monitor-serve.service`), so the board is reachable from any device on your Tailscale tailnet at the serving host's `100.x` address.

On the serving host:

```bash
tailscale ip -4
# e.g. 100.73.151.113 → http://100.73.151.113:8765/board.html

tailscale status --json | python3 -c "import json,sys; print(json.load(sys.stdin)['Self']['DNSName'].rstrip('.'))"
# e.g. eriks-macbook-pro.tailc50b43.ts.net → http://eriks-macbook-pro.tailc50b43.ts.net:8765/board.html
```

`make status-host` and `scripts/serve_board.py` print tailnet URLs when Tailscale is installed.

**Security notes:**

- Only `board.html` is exposed; `prices.jsonl` and other data files return 403.
- Tailscale ACLs control which tailnet devices can reach port `8765`. No extra macOS firewall rule is usually needed when the process listens on `*:8765`.
- If an older install bound `127.0.0.1`, run `make install-scheduler` (or reload the serve unit) after upgrading so it picks up `--host 0.0.0.0`.

### Sharing the board

| Audience | URL | Notes |
|----------|-----|-------|
| This machine | `http://127.0.0.1:8765/board.html` | Local only |
| Tailnet peers | `http://eriks-macbook-pro.tailc50b43.ts.net:8765/board.html` | MagicDNS; requires Tailscale on the viewer's device |
| Tailnet peers (IP) | `http://100.73.151.113:8765/board.html` | Same as above; use if MagicDNS is unavailable |
| **Anyone with the link** | `https://eriks-macbook-pro.tailc50b43.ts.net/seafood/board.html` | Public HTTPS via [Tailscale Funnel](https://tailscale.com/kb/1223/tailscale-funnel); read-only `board.html` |

**Recommended share links**

- **Tailnet only** (family/devices on your tailnet): `http://eriks-macbook-pro.tailc50b43.ts.net:8765/board.html`
- **Public internet** (no Tailscale required): `https://eriks-macbook-pro.tailc50b43.ts.net/seafood/board.html`

Only `board.html` is exposed; `prices.jsonl` and other data files return 403. Funnel does not publish JSONL or scrape logs.

**Enable or refresh public Funnel** (on the serving host, board already on `:8765`):

```bash
tailscale funnel --bg --yes --set-path=/seafood 8765
tailscale funnel status
# → https://<your-host>.ts.net/seafood/board.html
```

To stop public access while keeping tailnet reachability: `tailscale funnel reset` (removes all funnel routes on this node; re-add other funnel paths if needed).

`make status-host` prints localhost, LAN, and tailnet URLs when Tailscale is installed.

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

Runtime data lives in `data/` (git-ignored): `prices.jsonl`, `quarantine.jsonl`, `run-log.jsonl`, `market-coverage.json`. **`data/board.html` is tracked** so a dev machine can scrape and push today's board for the serving host to pull (see [Dev machine vs serving host](#dev-machine-vs-serving-host) below).

## Secrets / cookies

| Secret | Path | Purpose |
|---|---|---|
| Telegram bot token | `~/.openclaw/secrets/telegram/herb.token` | Price-drop alerts (`--alerts` only) |
| Telegram chat ID | `~/.openclaw/secrets/telegram/chat_id` or env `LOBSTER_TELEGRAM_CHAT_ID` | Alert destination |
| Facebook cookies | `~/.openclaw/secrets/facebook-cookies.json` | Unlock FB-only markets |
| Google CSE | env / `google_cse.py` config | Search fallback before DDG |

### Facebook cookies unlock path (D-01)

Six markets are FB-only (Ancient Mariner, Two Tides, Scarborough, Free Range, SoPo, Five Islands). Without cookies they stay blocked; DDG/CSE fallbacks are captcha-prone.

**How it works:**

1. `scripts/secrets.py` loads `~/.openclaw/secrets/facebook-cookies.json` when present (dict `c_user`/`xs`, nested `cookies`, or browser-export list format).
2. `scripts/scrape_markets.py` passes those cookies to `fb_curl_fetch.fetch_fb_posts()` first, then `facebook-scraper` as fallback.
3. `scripts/fb_curl_fetch.py` uses the same `load_fb_cookies()` path — no separate cookie file.

**Setup:** See [setup_fb_cookies.md](setup_fb_cookies.md). Verify with:

```bash
.venv/bin/python -c "from secrets import load_fb_cookies; print('cookies OK' if load_fb_cookies() else 'missing')"
bash scripts/preflight_secrets.sh
```

**Without cookies:** Pine Tree and Harbor Fish (web catalogs) still serve live prices; blocked markets appear in SOURCE COVERAGE with reasons.

## Scheduling

**Install path requirement (macOS launchd):** Clone and run the repo **outside** `~/Documents` — e.g. `~/lobster-price-monitor` or `/opt/lobster-price-monitor`. macOS TCC blocks launchd from executing scripts under `~/Documents` (exit 78 / `Operation not permitted`). Set `LOBSTER_ROOT` to this path before `make install-scheduler`.

Set `LOBSTER_ROOT` to your install path (e.g. `/opt/lobster-price-monitor` on Linux or `/Users/you/lobster-price-monitor` on macOS). Canonical unit templates use the `LOBSTER_ROOT` placeholder on **both** macOS and Linux — substitute at install time (see `scripts/install_scheduler.sh`).

| Platform | Scrape | Scrape (ops / alerts) | Serve | Health log |
|----------|--------|----------------------|-------|------------|
| Linux systemd | `deploy/systemd/lobster-price-monitor-scrape.service` + `.timer` | `deploy/systemd/lobster-price-monitor-scrape.ops.service` + `.ops.timer` | `deploy/systemd/lobster-price-monitor-serve.service` | `lobster-price-monitor-health.service` + `.timer` |
| macOS launchd | `deploy/launchd/com.erik.lobster-price-monitor.scrape.plist` (Label: `…scrape`) | `deploy/launchd/com.erik.lobster-price-monitor.scrape.ops.plist` (Label: `…scrape.ops`) | `deploy/launchd/com.erik.lobster-price-monitor.serve.plist` | `com.erik.lobster-price-monitor.health.plist` |
| cron | `deploy/crontab.example` (`run_scrape.sh`, no alerts) | `LOBSTER_ALERTS=1` + `run_scrape.sh` (see commented ops block) | run serve via systemd/launchd or `@reboot` | manual or health unit |

**Watchdog (ops, Wave 9):** `deploy/launchd/com.erik.lobster-price-monitor.watchdog.plist` or `deploy/systemd/lobster-price-monitor-watchdog.service` + `.timer`. Installed automatically on `make promote-ops`; opt in on dry-run with `install_scheduler.sh --with-watchdog`.

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

### Five Islands (one command)

```bash
make import-five-islands
```

Imports soft shell **$14.99/lb** and hard shell **$15.99/lb** for Five Islands Lobster Co. (baseline wharf prices; verify against reality before serving).

### Serving host workflow

`prices.jsonl` is gitignored — manual imports exist only in local `data/`. After `git pull` on the serving host, re-run imports if Five Islands rows are missing:

```bash
cd "$LOBSTER_ROOT"
make import-five-islands
make verify-deploy          # confirms board.html matches data, no demo markers
make status-host
```

If the host runs its own scrape scheduler, a scrape will **not** remove manual rows (they persist in `prices.jsonl`), but you must re-import after a fresh clone or `data/` wipe.

### Individual imports

Run from the repo root:

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

## Dev machine vs serving host

**July 2026 handoff:** Erik's Cursor dev laptop (`~/Documents/.../lobster-price-monitor`) is **not** the production serving host. Use it to scrape and publish `data/board.html`; the Mac mini / Chromebox pulls and serves.

### Why the dev laptop board went stale (2026-07-06)

- `data/board.html` on the dev machine was last regenerated **2026-07-05** (~11:46 PM ET) before Monday's board.
- launchd scrape (`com.erik.lobster-price-monitor.scrape`) was loaded but **failed with exit 78** (`EX_CONFIG`). `logs/scrape.err` showed:
  - `getcwd: cannot access parent directories: Operation not permitted`
  - `run_scrape.sh: Operation not permitted`
- **Cause:** macOS privacy (TCC) blocks launchd from executing scripts under `~/Documents/` unless Terminal (or `launchd`) has **Full Disk Access**. Manual scrapes from Cursor/Terminal work; scheduled launchd jobs do not.
- **Do not serve from the dev laptop long-term.** Stop any manual `serve_board.py` after testing; production serve stays on the dedicated host.

### Publish today's board from dev → pull on serving host

On the **dev machine** (after `bash scripts/dry_run.sh` or `scrape_markets.py --no-alerts`):

```bash
git add data/board.html .gitignore DEPLOYMENT.md
git commit -m "Publish Monday board"
gpa   # or: GIT_PUSH_ALLOWED=1 git push
```

On the **serving host** (Mac mini / Chromebox):

```bash
cd "$LOBSTER_ROOT"
git pull
make import-five-islands    # Five Islands rows are local-only (not in git)
# Optional same-machine handoff when dev scraped but serving host is ~/lobster-price-monitor:
# make sync-scrape-state SOURCE_DATA=/path/to/dev/repo/data
make upgrade-host           # or restart serve if only board.html changed
```

### Why `:8765` can show only 3 specials (2026-07-06 QA)

launchd **serve** runs from `$LOBSTER_ROOT` (e.g. `~/lobster-price-monitor`), **not** the Cursor dev clone under `~/Documents/...`. Those are separate `data/prices.jsonl` files (gitignored).

| Location | Typical board specials | Why |
|----------|------------------------|-----|
| Dev clone (`~/Documents/...`) | ~23 (25 gated) | Full scrape history + web catalogs |
| Serving host (`~/lobster-price-monitor`) | **3** before sync | Fresh clone; last scrape deduped 11 rows; only web+1 FB row gated |

**Fix:** `git pull` for `data/board.html`, or copy scrape state:

```bash
make sync-scrape-state SOURCE_DATA=/path/to/dev/repo/data
```

Hard-refresh the browser after serve picks up the new `board.html`.

```bash
git pull
# board.html is now in data/ — serve unit reads it automatically
make status-host          # confirm scrape age + serve URL
curl -sf http://127.0.0.1:8765/board.html | head -c 200
```

If the serving host runs its own scrape scheduler, a local scrape will overwrite `board.html` on the next tick — that is expected and preferred once schedulers are healthy there. Until then, the git-pushed board is the handoff path.

### Fix launchd scrape on macOS (serving host or any Mac)

1. Install the repo **outside** `~/Documents` (e.g. `~/lobster-price-monitor` or `/opt/lobster-price-monitor`), **or**
2. Grant **Full Disk Access** to the process launchd uses (often requires moving the job to a path launchd can read), **or**
3. Use **cron** or a manual scrape + git publish workflow from an interactive shell.

Verify after fix: `launchctl print gui/$(id -u)/com.erik.lobster-price-monitor.scrape` should show `last exit code = 0` after the next scheduled run, and `logs/scrape.err` should be empty.
