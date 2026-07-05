# NEXT_AGENT.md — Host Deployment Handoff

**Status:** Code complete on `main` (Gates AAA → D pass in CI). This runbook is for the production-host agent deploying to Mac mini or Linux Chromebox.

See also: [DEPLOYMENT.md](DEPLOYMENT.md) (reference), [RALPH.md](RALPH.md) (project context), [setup_fb_cookies.md](setup_fb_cookies.md) (FB cookies).

---

## Prerequisites

- Python 3.11+ on target host (3.14 tested locally)
- Repo cloned to install path (set `LOBSTER_ROOT`, e.g. `/opt/lobster-price-monitor` or `~/lobster-price-monitor`)
- Network access to configured web catalogs

### Secrets (`~/.openclaw/secrets/`)

| Secret | Path | Required for |
|--------|------|--------------|
| Telegram bot token | `telegram/herb.token` | Live alerts (Gate D ops) |
| Telegram chat ID | `telegram/chat_id` or env `LOBSTER_TELEGRAM_CHAT_ID` | Alert destination |
| Facebook cookies | `facebook-cookies.json` | Optional — unlocks 6 FB-only markets |
| Google CSE key + CX | `google-cse.key`, `google-cse.cx` | Search fallback before DDG |

Copy [.env.example](.env.example) to `.env` locally if you prefer env-based config (secrets files remain primary).

---

## Phase 1 — Install and smoke (dry-run, no alerts)

```bash
export LOBSTER_ROOT=/path/to/lobster-price-monitor
cd "$LOBSTER_ROOT"

bash scripts/install.sh
bash scripts/dry_run.sh
make verify
make verify-production-ci   # CI-safe Gate C smoke
make verify-ops-ci          # CI-safe Gate D smoke
.venv/bin/python scripts/health_check.py
make serve                  # confirm http://127.0.0.1:8765/board.html
```

**Alerts are off by default.** Do not enable Telegram until Phase 3.

---

## Phase 2 — Scheduler (dry-run first)

1. Edit `LOBSTER_ROOT` placeholders in unit files under [deploy/launchd/](deploy/launchd/) or [deploy/systemd/](deploy/systemd/).
2. Install and enable units:

**macOS (launchd):**

```bash
# Replace LOBSTER_ROOT in plists, then copy to LaunchAgents
cp deploy/launchd/com.erik.lobster-price-monitor.scrape.plist ~/Library/LaunchAgents/
cp deploy/launchd/com.erik.lobster-price-monitor.serve.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.erik.lobster-price-monitor.scrape.plist
launchctl load ~/Library/LaunchAgents/com.erik.lobster-price-monitor.serve.plist
```

Labels: `com.erik.lobster-price-monitor.scrape`, `com.erik.lobster-price-monitor.serve`

**Linux (systemd):**

```bash
sudo cp deploy/systemd/lobster-price-monitor-scrape.service /etc/systemd/system/
sudo cp deploy/systemd/lobster-price-monitor-scrape.timer /etc/systemd/system/
sudo cp deploy/systemd/lobster-price-monitor-serve.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now lobster-price-monitor-scrape.timer
sudo systemctl enable --now lobster-price-monitor-serve.service
```

3. Confirm scheduler on host:

```bash
make verify-production
```

---

## Phase 3 — Ops promotion (live Telegram)

Requires `~/.openclaw/secrets/telegram/herb.token` and chat ID configured.

```bash
# Preview planned actions without changing the host scheduler
bash scripts/promote_ops.sh --dry-run

# Promote: unload dry-run → load ops → confirm scrape → verify
make promote-ops

# Host gate: ops loaded, dry-run unloaded, secrets OK
make verify-ops
```

`promote_ops.sh` swaps dry-run scheduler for ops scheduler (`LOBSTER_ALERTS=1`), runs one confirmation scrape with alerts, then runs `make verify-ops`.

---

## Phase 4 — Ongoing ops

| Task | Command |
|------|---------|
| Health check | `.venv/bin/python scripts/health_check.py` |
| Health log (daily) | `.venv/bin/python scripts/health_check.py --log` |
| Manual scrape (no alerts) | `make scrape` |
| Five Islands workaround | `scripts/manual_import.py` |
| FB cookies setup | [setup_fb_cookies.md](setup_fb_cookies.md) |
| Update RALPH learnings | `.venv/bin/python scripts/update_ralph_learnings.py` |

**Cadence:** Weekdays 4×/day (07, 11, 15, 19 ET); weekends 2×/day (09, 17 ET).

---

## Gate command reference

| Gate | Host | CI-safe |
|------|------|---------|
| AAA | `make verify` | `make verify-ci` |
| B+ | `make verify-next` | `make verify-next-ci` |
| C (Production) | `make verify-production` | `make verify-production-ci` |
| D (Ops) | `make verify-ops` | `make verify-ops-ci` |

`make verify-production` accepts either dry-run or ops scrape scheduler on a promoted host. `make verify-ops` requires the **ops** scheduler loaded and dry-run **unloaded**.

---

## Known blockers (do not re-investigate)

- **Five Islands** has no live $/lb online — board correctly empty until manual import or cookies
- **Unauthenticated FB** returns 0 posts — use cookies or rely on web-catalog sources (Pine Tree, Harbor Fish)
- **Use MoscaGemBot** token at `~/.openclaw/secrets/telegram/herb.token`, NOT CronBot
- **DDG fallback** is captcha-prone without cookies — Google CSE preferred when configured

---

## Maintainer tools

| Tool | Purpose |
|------|---------|
| `make regen-bplus-fixtures` | Regenerate CI Gate B+ fixture data (maintainer-only) |
| `scripts/send_test_alert.py` | Send live Telegram test alerts — **not a unit test** |

---

## Out of scope for deploy agent

- No Docker/K8s/PaaS configs — bare-metal deployment only
- No reverse-proxy/TLS templates — add nginx or Caddy if exposing beyond LAN
- Remote `cursor/gate-d-*` branches are absorbed into `main`; safe to delete after confirm
