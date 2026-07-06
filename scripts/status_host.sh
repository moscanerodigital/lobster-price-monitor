#!/usr/bin/env bash
# Gate D Wave 8 host status — unified scheduler, health, and scrape diagnostics.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOBSTER_ROOT="${LOBSTER_ROOT:-$ROOT}"
DRY_RUN=false
JSON_OUTPUT=false
SERVE_PORT="${LOBSTER_SERVE_PORT:-8765}"

OPS_SCRAPE_LABEL="com.erik.lobster-price-monitor.scrape.ops"
DRY_RUN_SCRAPE_LABEL="com.erik.lobster-price-monitor.scrape"
SERVE_LABEL="com.erik.lobster-price-monitor.serve"
HEALTH_LABEL="com.erik.lobster-price-monitor.health"
OPS_SCRAPE_TIMER="lobster-price-monitor-scrape.ops.timer"
DRY_RUN_SCRAPE_TIMER="lobster-price-monitor-scrape.timer"
HEALTH_TIMER="lobster-price-monitor-health.timer"
SERVE_SERVICE="lobster-price-monitor-serve.service"

SCHEDULER_MODE="none"
GIT_REVISION=""
SCRAPE_TS=""
SCRAPE_AGE_HOURS=""
SCRAPE_STALE=false
HEALTH_JSON="{}"
SECRETS_OK=true
DEGRADED=false
FATAL=false

SCRAPE_UNIT_LOADED=false
SCRAPE_UNIT_ACTIVE=false
SERVE_LOADED=false
SERVE_ACTIVE=false
HEALTH_LOADED=false

usage() {
  cat <<'EOF'
Usage: scripts/status_host.sh [--dry-run] [--json] [--lobster-root PATH]

Unified host status report:
  - LOBSTER_ROOT preflight and venv
  - Scheduler mode (none / dry-run / ops) and unit status
  - Git revision (when .git exists)
  - Scrape freshness from run-log.jsonl
  - health_check.py report
  - Serve endpoints (localhost + LAN)
  - Secrets preflight summary (non-fatal)

Exit codes: 0 healthy, 1 degraded, 2 fatal preflight error.

Set LOBSTER_ROOT to override install path (default: repo root).
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    --json)
      JSON_OUTPUT=true
      shift
      ;;
    --lobster-root)
      LOBSTER_ROOT="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

log() {
  if [[ "$JSON_OUTPUT" == false ]]; then
    echo "$@"
  else
    echo "$@" >&2
  fi
}

ops_loaded() {
  case "$(uname -s)" in
    Darwin)
      launchctl list 2>/dev/null | grep -q "${OPS_SCRAPE_LABEL}$"
      ;;
    Linux)
      systemctl is-enabled "$OPS_SCRAPE_TIMER" &>/dev/null
      ;;
    *)
      return 1
      ;;
  esac
}

dry_run_loaded() {
  case "$(uname -s)" in
    Darwin)
      launchctl list 2>/dev/null | grep -q "${DRY_RUN_SCRAPE_LABEL}$"
      ;;
    Linux)
      systemctl is-enabled "$DRY_RUN_SCRAPE_TIMER" &>/dev/null
      ;;
    *)
      return 1
      ;;
  esac
}

detect_scheduler_mode() {
  if ops_loaded; then
    SCHEDULER_MODE="ops"
  elif dry_run_loaded; then
    SCHEDULER_MODE="dry-run"
  else
    SCHEDULER_MODE="none"
  fi
}

launchctl_pid() {
  local label="$1"
  launchctl list 2>/dev/null | awk -v lbl="$label" '$3 == lbl { print $1; exit }'
}

check_unit_status() {
  if [[ "$DRY_RUN" == true ]]; then
    log "[dry-run] check scheduler units (scrape, serve, health)"
    return 0
  fi

  case "$(uname -s)" in
    Darwin)
      local scrape_label=""
      case "$SCHEDULER_MODE" in
        ops) scrape_label="$OPS_SCRAPE_LABEL" ;;
        dry-run) scrape_label="$DRY_RUN_SCRAPE_LABEL" ;;
      esac

      if [[ -n "$scrape_label" ]]; then
        if launchctl list 2>/dev/null | grep -q "${scrape_label}$"; then
          SCRAPE_UNIT_LOADED=true
          local pid
          pid="$(launchctl_pid "$scrape_label")"
          if [[ -n "$pid" && "$pid" != "-" ]]; then
            SCRAPE_UNIT_ACTIVE=true
          fi
        fi
      fi

      if launchctl list 2>/dev/null | grep -q "${SERVE_LABEL}$"; then
        SERVE_LOADED=true
        local serve_pid
        serve_pid="$(launchctl_pid "$SERVE_LABEL")"
        if [[ -n "$serve_pid" && "$serve_pid" != "-" ]]; then
          SERVE_ACTIVE=true
        fi
      fi

      if launchctl list 2>/dev/null | grep -q "${HEALTH_LABEL}$"; then
        HEALTH_LOADED=true
      fi
      ;;
    Linux)
      local scrape_timer=""
      case "$SCHEDULER_MODE" in
        ops) scrape_timer="$OPS_SCRAPE_TIMER" ;;
        dry-run) scrape_timer="$DRY_RUN_SCRAPE_TIMER" ;;
      esac

      if [[ -n "$scrape_timer" ]]; then
        if systemctl is-enabled "$scrape_timer" &>/dev/null; then
          SCRAPE_UNIT_LOADED=true
          SCRAPE_UNIT_ACTIVE=true
        fi
      fi

      if systemctl is-enabled "$SERVE_SERVICE" &>/dev/null; then
        SERVE_LOADED=true
      fi
      if systemctl is-active "$SERVE_SERVICE" &>/dev/null; then
        SERVE_ACTIVE=true
      fi

      if systemctl is-enabled "$HEALTH_TIMER" &>/dev/null; then
        HEALTH_LOADED=true
      fi
      ;;
    *)
      log "WARNING: unknown OS $(uname -s) — skipping unit checks"
      ;;
  esac
}

preflight() {
  if [[ ! -d "$LOBSTER_ROOT" ]]; then
    echo "ERROR: LOBSTER_ROOT does not exist: $LOBSTER_ROOT" >&2
    FATAL=true
    return 1
  fi
  if [[ ! -w "$LOBSTER_ROOT" ]]; then
    echo "ERROR: LOBSTER_ROOT is not writable: $LOBSTER_ROOT" >&2
    FATAL=true
    return 1
  fi
  if [[ "$DRY_RUN" == true ]]; then
    log "[dry-run] check venv at ${LOBSTER_ROOT}/.venv"
    log "[dry-run] check writable data/ under ${LOBSTER_ROOT}"
    return 0
  fi
  if [[ ! -x "${LOBSTER_ROOT}/.venv/bin/python" ]]; then
    echo "ERROR: venv not found at ${LOBSTER_ROOT}/.venv — run scripts/bootstrap_host.sh first" >&2
    FATAL=true
    return 1
  fi
  mkdir -p "${LOBSTER_ROOT}/data"
  if [[ ! -w "${LOBSTER_ROOT}/data" ]]; then
    echo "ERROR: data/ is not writable under $LOBSTER_ROOT" >&2
    FATAL=true
    return 1
  fi
  return 0
}

collect_git_revision() {
  if [[ "$DRY_RUN" == true ]]; then
    GIT_REVISION="dry-run"
    return 0
  fi
  if [[ -d "${LOBSTER_ROOT}/.git" ]]; then
    GIT_REVISION="$(git -C "$LOBSTER_ROOT" rev-parse --short HEAD 2>/dev/null || echo "unknown")"
  else
    GIT_REVISION="n/a"
  fi
}

collect_scrape_freshness() {
  if [[ "$DRY_RUN" == true ]]; then
    SCRAPE_TS="dry-run"
    SCRAPE_AGE_HOURS="0"
    return 0
  fi

  local py="${LOBSTER_ROOT}/.venv/bin/python"
  local result
  result="$("$py" - <<'PY'
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

root = Path(sys.argv[1])
run_log = root / "data" / "run-log.jsonl"
if not run_log.exists() or run_log.stat().st_size == 0:
    print("||")
    raise SystemExit(0)

last_ts = None
for line in run_log.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line:
        continue
    try:
        row = json.loads(line)
    except json.JSONDecodeError:
        continue
    ts = row.get("ts")
    if ts:
        last_ts = ts

if not last_ts:
    print("||")
    raise SystemExit(0)

s = str(last_ts).replace("Z", "+00:00")
try:
    dt = datetime.fromisoformat(s)
except ValueError:
    print(f"{last_ts}||")
    raise SystemExit(0)

if dt.tzinfo is None:
    dt = dt.replace(tzinfo=timezone.utc)
now = datetime.now(timezone.utc)
age_h = (now - dt).total_seconds() / 3600.0
stale = age_h > 24.0
print(f"{last_ts}|{age_h:.1f}|{1 if stale else 0}")
PY
"$LOBSTER_ROOT")"

  SCRAPE_TS="${result%%|*}"
  local rest="${result#*|}"
  SCRAPE_AGE_HOURS="${rest%%|*}"
  local stale_flag="${rest##*|}"
  if [[ "$stale_flag" == "1" ]]; then
    SCRAPE_STALE=true
  fi
}

collect_health() {
  if [[ "$DRY_RUN" == true ]]; then
    HEALTH_JSON='{"status":"dry-run","latest_run_timestamp":null,"live_markets":[],"blocked_markets":[]}'
    return 0
  fi

  local py="${LOBSTER_ROOT}/.venv/bin/python"
  local health_out
  health_out="$("$py" "${LOBSTER_ROOT}/scripts/health_check.py" 2>/dev/null || true)"
  if [[ -z "$health_out" ]]; then
    HEALTH_JSON='{"status":"unknown"}'
    return 0
  fi
  HEALTH_JSON="$health_out"
}

collect_secrets_summary() {
  if [[ "$DRY_RUN" == true ]]; then
    log "[dry-run] bash scripts/preflight_secrets.sh --dry-run"
    return 0
  fi

  if ! bash "${LOBSTER_ROOT}/scripts/preflight_secrets.sh" >/dev/null 2>&1; then
    SECRETS_OK=false
  fi
}

lan_ip() {
  if [[ "$DRY_RUN" == true ]]; then
    echo "127.0.0.1"
    return 0
  fi
  "${LOBSTER_ROOT}/.venv/bin/python" - <<'PY'
import socket
try:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    print(s.getsockname()[0])
    s.close()
except OSError:
    print("127.0.0.1")
PY
}

evaluate_degraded() {
  if [[ "$DRY_RUN" == true ]]; then
    return 0
  fi

  local health_status
  health_status="$("${LOBSTER_ROOT}/.venv/bin/python" -c "import json,sys; print(json.loads(sys.argv[1]).get('status','unknown'))" "$HEALTH_JSON")"

  if [[ "$health_status" != "ready" ]]; then
    DEGRADED=true
  fi

  if [[ "$SCRAPE_STALE" == true ]]; then
    DEGRADED=true
  fi

  case "$SCHEDULER_MODE" in
    dry-run|ops)
      if [[ "$SCRAPE_UNIT_LOADED" != true ]]; then
        DEGRADED=true
      fi
      if [[ "$SERVE_LOADED" != true || "$SERVE_ACTIVE" != true ]]; then
        DEGRADED=true
      fi
      ;;
  esac
}

print_human_report() {
  log "=== Gate D Wave 8 host status ==="
  log ""
  log "--- Preflight ---"
  log "LOBSTER_ROOT: ${LOBSTER_ROOT}"
  if [[ "$DRY_RUN" == true ]]; then
    log "[dry-run] venv and data/ checks skipped"
  else
    log "venv: ${LOBSTER_ROOT}/.venv"
    log "data/: writable"
  fi
  log ""
  log "--- Scheduler ---"
  log "Scheduler mode: ${SCHEDULER_MODE}"
  if [[ "$DRY_RUN" == true ]]; then
    log "[dry-run] unit status checks skipped"
  else
    log "Scrape unit loaded: ${SCRAPE_UNIT_LOADED}"
    log "Scrape unit active: ${SCRAPE_UNIT_ACTIVE}"
    log "Serve loaded: ${SERVE_LOADED}"
    log "Serve active: ${SERVE_ACTIVE}"
    log "Health timer loaded: ${HEALTH_LOADED}"
  fi
  log ""
  log "--- Code ---"
  log "Git revision: ${GIT_REVISION}"
  log ""
  log "--- Scrape freshness ---"
  if [[ -n "$SCRAPE_TS" && "$SCRAPE_TS" != "||" ]]; then
    log "Latest scrape: ${SCRAPE_TS}"
    if [[ -n "$SCRAPE_AGE_HOURS" ]]; then
      log "Scrape age: ${SCRAPE_AGE_HOURS}h"
    fi
    if [[ "$SCRAPE_STALE" == true ]]; then
      log "WARNING: scrape stale (>24h)"
    fi
  else
    log "No run-log entries yet"
  fi
  log ""
  log "--- Health ---"
  if [[ "$DRY_RUN" == true ]]; then
    log "[dry-run] health_check.py skipped"
  else
    log "$HEALTH_JSON"
  fi
  log ""
  log "--- Serve ---"
  local lan
  lan="$(lan_ip)"
  log "Local:  http://127.0.0.1:${SERVE_PORT}/board.html"
  log "LAN:    http://${lan}:${SERVE_PORT}/board.html"
  log ""
  log "--- Secrets ---"
  if [[ "$DRY_RUN" == true ]]; then
    log "[dry-run] secrets preflight skipped"
  elif [[ "$SECRETS_OK" == true ]]; then
    log "Secrets preflight: OK"
  else
    log "Secrets preflight: warnings or missing optional secrets"
  fi
  log ""
  if [[ "$DEGRADED" == true ]]; then
    log "=== Host status: DEGRADED ==="
  else
    log "=== Host status: HEALTHY ==="
  fi
}

print_json_report() {
  local lan
  lan="$(lan_ip)"

  if [[ "$DRY_RUN" == true ]]; then
    cat <<EOF
{"lobster_root":"${LOBSTER_ROOT}","dry_run":true,"scheduler_mode":"${SCHEDULER_MODE}","git_revision":"${GIT_REVISION}","scrape":{"timestamp":"${SCRAPE_TS}","age_hours":0,"stale":false},"health":{"status":"dry-run"},"serve":{"local":"http://127.0.0.1:${SERVE_PORT}/board.html","lan":"http://${lan}:${SERVE_PORT}/board.html"},"secrets_ok":true,"status":"dry-run"}
EOF
    return 0
  fi

  LOBSTER_ROOT="$LOBSTER_ROOT" \
  SCHEDULER_MODE="$SCHEDULER_MODE" \
  GIT_REVISION="$GIT_REVISION" \
  SCRAPE_TS="$SCRAPE_TS" \
  SCRAPE_AGE_HOURS="$SCRAPE_AGE_HOURS" \
  SCRAPE_STALE="$SCRAPE_STALE" \
  SCRAPE_UNIT_LOADED="$SCRAPE_UNIT_LOADED" \
  SCRAPE_UNIT_ACTIVE="$SCRAPE_UNIT_ACTIVE" \
  SERVE_LOADED="$SERVE_LOADED" \
  SERVE_ACTIVE="$SERVE_ACTIVE" \
  HEALTH_LOADED="$HEALTH_LOADED" \
  HEALTH_JSON="$HEALTH_JSON" \
  SERVE_PORT="$SERVE_PORT" \
  LAN_IP="$lan" \
  SECRETS_OK="$SECRETS_OK" \
  DEGRADED="$DEGRADED" \
  "${LOBSTER_ROOT}/.venv/bin/python" - <<'PY'
import json
import os

health = json.loads(os.environ.get("HEALTH_JSON", "{}"))

age_val = None
scrape_age = os.environ.get("SCRAPE_AGE_HOURS", "")
if scrape_age:
    try:
        age_val = float(scrape_age)
    except ValueError:
        age_val = None

scrape_ts = os.environ.get("SCRAPE_TS", "")
serve_port = os.environ.get("SERVE_PORT", "8765")
lan_ip = os.environ.get("LAN_IP", "127.0.0.1")
degraded = os.environ.get("DEGRADED", "false") == "true"

report = {
    "lobster_root": os.environ.get("LOBSTER_ROOT", ""),
    "dry_run": False,
    "scheduler_mode": os.environ.get("SCHEDULER_MODE", "none"),
    "git_revision": os.environ.get("GIT_REVISION", ""),
    "units": {
        "scrape_loaded": os.environ.get("SCRAPE_UNIT_LOADED", "false") == "true",
        "scrape_active": os.environ.get("SCRAPE_UNIT_ACTIVE", "false") == "true",
        "serve_loaded": os.environ.get("SERVE_LOADED", "false") == "true",
        "serve_active": os.environ.get("SERVE_ACTIVE", "false") == "true",
        "health_loaded": os.environ.get("HEALTH_LOADED", "false") == "true",
    },
    "scrape": {
        "timestamp": scrape_ts or None,
        "age_hours": age_val,
        "stale": os.environ.get("SCRAPE_STALE", "false") == "true",
    },
    "health": {
        "status": health.get("status", "unknown"),
        "latest_run_timestamp": health.get("latest_run_timestamp"),
        "live_markets": health.get("live_markets", []),
        "blocked_markets": health.get("blocked_markets", []),
    },
    "serve": {
        "local": f"http://127.0.0.1:{serve_port}/board.html",
        "lan": f"http://{lan_ip}:{serve_port}/board.html",
    },
    "secrets_ok": os.environ.get("SECRETS_OK", "true") == "true",
    "status": "degraded" if degraded else "healthy",
}
print(json.dumps(report, ensure_ascii=False))
PY
}

main() {
  if ! preflight; then
    if [[ "$JSON_OUTPUT" == true ]]; then
      echo '{"status":"fatal","error":"preflight failed"}' >&2
      echo '{"status":"fatal"}'
    fi
    exit 2
  fi

  detect_scheduler_mode
  check_unit_status
  collect_git_revision
  collect_scrape_freshness
  collect_health
  collect_secrets_summary
  evaluate_degraded

  if [[ "$JSON_OUTPUT" == true ]]; then
    print_json_report
  else
    print_human_report
  fi

  if [[ "$DRY_RUN" == true ]]; then
    exit 0
  fi
  if [[ "$DEGRADED" == true ]]; then
    exit 1
  fi
  exit 0
}

main
