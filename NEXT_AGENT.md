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

## Quick start (all phases)

Preview the full host deploy path:

```bash
export LOBSTER_ROOT=/path/to/lobster-price-monitor
cd "$LOBSTER_ROOT"

bash scripts/deploy_host.sh --dry-run --phase all          # phases 1–2
bash scripts/deploy_host.sh --dry-run --phase all --promote # includes phase 3
```

Run for real (phase 3 requires Telegram secrets):

```bash
make deploy-host                    # phases 1–2
make deploy-host -- --promote       # phases 1–2–3 (live alerts)
```

---

## Phase 1 — Install and smoke (dry-run, no alerts)

**Recommended (one command):**

```bash
export LOBSTER_ROOT=/path/to/lobster-price-monitor
cd "$LOBSTER_ROOT"

make bootstrap-host
# or: bash scripts/bootstrap_host.sh
```

This runs install, dry-run scrape, verify gates, health check, and a serve smoke test (curl `board.html` on port 8765).

**Manual fallback:**

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

**Recommended (one command):**

```bash
# Preview planned actions
bash scripts/install_scheduler.sh --dry-run

# Install dry-run scrape + serve + daily health-log schedulers
make install-scheduler
# or: bash scripts/install_scheduler.sh

# Confirm deploy gate (dry-run loaded, ops not yet promoted)
make verify-deploy
```

`install_scheduler.sh` substitutes `LOBSTER_ROOT` into launchd plists (macOS) or systemd units (Linux), loads scrape + serve, and optionally installs the daily health-log unit. Pass `--skip-health` for minimal install.

**Manual fallback (macOS):**

```bash
# Replace LOBSTER_ROOT in plists, then copy to LaunchAgents
cp deploy/launchd/com.erik.lobster-price-monitor.scrape.plist ~/Library/LaunchAgents/
cp deploy/launchd/com.erik.lobster-price-monitor.serve.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.erik.lobster-price-monitor.scrape.plist
launchctl load ~/Library/LaunchAgents/com.erik.lobster-price-monitor.serve.plist
```

Labels: `com.erik.lobster-price-monitor.scrape`, `com.erik.lobster-price-monitor.serve`

**Manual fallback (Linux):**

```bash
# Substitute LOBSTER_ROOT in unit templates, then install
for f in deploy/systemd/lobster-price-monitor-scrape.service \
         deploy/systemd/lobster-price-monitor-scrape.timer \
         deploy/systemd/lobster-price-monitor-serve.service; do
  sed "s|LOBSTER_ROOT|${LOBSTER_ROOT}|g" "$f" | sudo tee "/etc/systemd/system/$(basename "$f")"
done
sudo systemctl daemon-reload
sudo systemctl enable --now lobster-price-monitor-scrape.timer
sudo systemctl enable --now lobster-price-monitor-serve.service
```

Confirm scheduler on host:

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

**Rollback to dry-run (disable live alerts):**

```bash
bash scripts/demote_ops.sh --dry-run   # preview
make demote-ops                        # unload ops → load dry-run → verify-deploy
```

`promote_ops.sh` swaps dry-run scheduler for ops scheduler (`LOBSTER_ALERTS=1`), runs one confirmation scrape with alerts, then runs `make verify-ops`.

**Full host teardown (remove all schedulers):**

```bash
bash scripts/teardown_host.sh --dry-run    # preview demote + uninstall
make teardown-host                         # demote ops if loaded → uninstall all units
make uninstall-scheduler                   # uninstall only (skip demote)
```

`teardown_host.sh` demotes ops to dry-run when needed, then unloads scrape (dry-run + ops), serve, and health schedulers. Pass `--purge-files` to remove installed plists/units from disk. Does not delete `.venv`, `data/`, or the repo.

---

## Phase 4 — Ongoing ops

| Task | Command |
|------|---------|
| Host status (scheduler, health, scrape age) | `make status-host` |
| Host auto-recovery (reload serve/scrape, trigger scrape) | `make recover-host` |
| Upgrade in place (git pull + deps + scheduler reload) | `make upgrade-host` |
| Health check | `.venv/bin/python scripts/health_check.py` |
| Health log (daily) | `.venv/bin/python scripts/health_check.py --log` |
| Manual scrape (no alerts) | `make scrape` |
| Five Islands workaround | `scripts/manual_import.py` |
| FB cookies setup | [setup_fb_cookies.md](setup_fb_cookies.md) |
| Update RALPH learnings | `.venv/bin/python scripts/update_ralph_learnings.py` |

**Cadence:** Weekdays 4×/day (07, 11, 15, 19 ET); weekends 2×/day (09, 17 ET).

### Upgrade in place (Gate D Wave 7)

After `git pull` on a running host, refresh code, dependencies, and scheduler units without changing dry-run vs ops mode or deleting `data/`:

```bash
# Preview planned actions
bash scripts/upgrade_host.sh --dry-run

# Run upgrade (pull → install → reload schedulers → scrape → verify)
make upgrade-host

# Non-git installs (tarball copy)
bash scripts/upgrade_host.sh --skip-pull
```

`upgrade_host.sh` detects scheduler mode (dry-run, ops, or none) and reloads matching units. Dry-run hosts run `make verify-deploy`; ops hosts run `make verify-ops`. Also available via `bash scripts/deploy_host.sh --upgrade`.

### Host status (Gate D Wave 8)

Read-only diagnostics for a running host:

```bash
# Human-readable report
make status-host

# JSON for scripting
bash scripts/status_host.sh --json

# Preview checks without executing
bash scripts/deploy_host.sh --dry-run --status
```

Reports scheduler mode (none/dry-run/ops), unit loaded/active state, git revision, scrape freshness (>24h warns), `health_check.py` summary, serve URLs, and secrets preflight. Exit codes: 0 healthy, 1 degraded, 2 fatal preflight.

### Host watchdog (Gate D Wave 9)

Status-driven Telegram alerts when the host is degraded or fatal:

```bash
# Check only (no Telegram)
make watchdog-host

# Preview alert without sending
bash scripts/watchdog_host.sh --notify --dry-run

# Send alert if unhealthy (requires Telegram secrets)
bash scripts/watchdog_host.sh --notify

# Via deploy orchestrator
bash scripts/deploy_host.sh --watchdog
```

Ops promotion (`make promote-ops`) installs a watchdog timer (2×/day) with `LOBSTER_WATCHDOG_ALERTS=1` and `LOBSTER_WATCHDOG_RECOVER=1` (auto-recovery before alert). Alerts are deduped for 6 hours per reason set. Dry-run Phase 2 hosts can opt in with `bash scripts/install_scheduler.sh --with-watchdog`.

### Closed-loop ops recovery (Gate D Wave 11)

The scheduled ops watchdog runs auto-recovery before alerting. If recovery fails, the Telegram alert includes `auto-recovery attempted`. To disable on a host, set `LOBSTER_WATCHDOG_RECOVER=0` in the watchdog unit and reload.

`make verify-ops` on a host also checks that the watchdog unit has recovery enabled.

### Recovery escalation (Gate D Wave 12)

When auto-recovery leaves the host degraded across multiple watchdog runs, escalation alerts fire:

```bash
# Preview deep recovery path
bash scripts/recover_host.sh --dry-run --deep

# Watchdog with deep recovery + escalation tracking
bash scripts/watchdog_host.sh --recover --deep-recover --notify
```

Ops watchdog units default to `LOBSTER_WATCHDOG_DEEP_RECOVER=1` (tier-2 `upgrade_host` after tier-1 recovery). Failure streak tracked in `data/host-health.jsonl`; escalation Telegram sent after 3 consecutive failures in 48h (`LOBSTER_WATCHDOG_ESCALATE_AFTER` to override). `status_host.sh --json` reports `watchdog_health.consecutive_failures`.

### Host auto-recovery (Gate D Wave 10)

Status-driven remediation when the host is degraded:

```bash
# Preview recovery actions
bash scripts/recover_host.sh --dry-run

# Run recovery (reload serve, scrape scheduler, trigger scrape as needed)
make recover-host

# Recovery + re-run health check
bash scripts/recover_host.sh --notify

# Deep recovery (tier-2 upgrade_host when tier-1 insufficient)
bash scripts/recover_host.sh --deep

# Via deploy orchestrator
bash scripts/deploy_host.sh --recover
```

Watchdog can attempt recovery before alerting: `bash scripts/watchdog_host.sh --recover --notify`. On ops hosts the scheduled watchdog enables this by default (`LOBSTER_WATCHDOG_RECOVER=1`). Set `LOBSTER_WATCHDOG_RECOVER=0` to return to alert-only.

**Teardown with purge:** `make teardown-host TEARDOWN_FLAGS=--purge-files` or `bash scripts/deploy_host.sh --teardown --purge-files`.

---

## Gate command reference

| Gate | Host | CI-safe |
|------|------|---------|
| AAA | `make verify` | `make verify-ci` |
| B+ | `make verify-next` | `make verify-next-ci` |
| Deploy | `make verify-deploy` | `make verify-deploy-ci` |
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
| `make deploy-host` | Unified orchestrator (phases 1–2; add `--promote` for phase 3) |
| `make bootstrap-host` | Phase 1 install + dry-run + verify + health |
| `make install-scheduler` | Install dry-run scrape + serve + health schedulers (Phase 2) |
| `make demote-ops` | Roll back ops scheduler to dry-run (no live alerts) |
| `make teardown-host` | Full teardown: demote ops if loaded → uninstall all schedulers |
| `make upgrade-host` | In-place upgrade: pull, refresh deps, reload schedulers |
| `make status-host` | Read-only host diagnostics (scheduler, health, scrape age) |
| `make recover-host` | Host auto-recovery for degraded states |
| `make watchdog-host` | Host watchdog check (add `--notify` for Telegram alert) |
| `make uninstall-scheduler` | Unload scrape/serve/health schedulers only |
| `scripts/preflight_secrets.sh` | Check secrets paths without printing values |
| `make regen-bplus-fixtures` | Regenerate CI Gate B+ fixture data (maintainer-only) |
| `scripts/send_test_alert.py` | Send live Telegram test alerts — **not a unit test** |

---

## Out of scope for deploy agent

- No Docker/K8s/PaaS configs — bare-metal deployment only
- No reverse-proxy/TLS templates — add nginx or Caddy if exposing beyond LAN
- Remote `cursor/gate-d-*` branches are absorbed into `main`; safe to delete after confirm
