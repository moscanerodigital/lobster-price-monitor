#!/usr/bin/env bash
# Gate D Wave 10/12 host recovery — status-driven remediation for degraded hosts.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOBSTER_ROOT="${LOBSTER_ROOT:-$ROOT}"
DRY_RUN=false
NOTIFY=false
FORCE=false
DEEP=false
DEEP_RECOVERY_ATTEMPTED=false

OPS_SCRAPE_LABEL="com.erik.lobster-price-monitor.scrape.ops"
DRY_RUN_SCRAPE_LABEL="com.erik.lobster-price-monitor.scrape"
SERVE_LABEL="com.erik.lobster-price-monitor.serve"
OPS_SCRAPE_TIMER="lobster-price-monitor-scrape.ops.timer"
DRY_RUN_SCRAPE_TIMER="lobster-price-monitor-scrape.timer"
SCHEDULER_MODE="none"

ACTIONS_TAKEN=()

usage() {
  cat <<'EOF'
Usage: scripts/recover_host.sh [--dry-run] [--notify] [--force] [--deep] [--deep-recover] [--lobster-root PATH]

Status-driven host auto-recovery for degraded states:
  1. Run status_host.sh --json
  2. If healthy, exit 0
  3. If fatal preflight, exit 2 (no auto-recovery)
  4. Tier 1: reload serve, reload scrape scheduler, trigger scrape, health check
  5. Tier 2 (when --deep/--deep-recover or LOBSTER_WATCHDOG_DEEP_RECOVER=1): upgrade_host
  6. Re-run status_host.sh and exit with its code
  7. Optional --notify: deduped Telegram summary of actions taken

Set LOBSTER_ROOT to override install path (default: repo root).
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    --notify)
      NOTIFY=true
      shift
      ;;
    --force)
      FORCE=true
      shift
      ;;
    --deep|--deep-recover)
      DEEP=true
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

if [[ "${LOBSTER_WATCHDOG_DEEP_RECOVER:-}" == "1" || "${LOBSTER_WATCHDOG_DEEP_RECOVER:-}" == "true" ]]; then
  DEEP=true
fi

log() {
  echo "$@"
}

run() {
  if [[ "$DRY_RUN" == true ]]; then
    echo "[dry-run] $*"
  else
    echo "+ $*"
    "$@"
  fi
}

substitute_unit() {
  local src="$1"
  local dest="$2"
  if [[ "$DRY_RUN" == true ]]; then
    echo "[dry-run] sed 's|LOBSTER_ROOT|${LOBSTER_ROOT}|g' $src > $dest"
  else
    sed "s|LOBSTER_ROOT|${LOBSTER_ROOT}|g" "$src" > "$dest"
  fi
}

install_linux_unit() {
  local src="$1"
  local name
  name="$(basename "$src")"
  local tmp
  tmp="$(mktemp)"
  substitute_unit "$src" "$tmp"
  if [[ "$DRY_RUN" == true ]]; then
    echo "[dry-run] sudo cp $tmp /etc/systemd/system/$name"
    rm -f "$tmp"
  else
    sudo cp "$tmp" "/etc/systemd/system/$name"
    rm -f "$tmp"
  fi
}

record_action() {
  ACTIONS_TAKEN+=("$1")
}

run_status() {
  local flags=(--json --lobster-root "$LOBSTER_ROOT")
  [[ "$DRY_RUN" == true ]] && flags+=(--dry-run)

  local status_out
  local status_code=0
  set +e
  status_out="$(bash "${LOBSTER_ROOT}/scripts/status_host.sh" "${flags[@]}" 2>/dev/null)"
  status_code=$?
  set -e

  STATUS_JSON="$status_out"
  STATUS_CODE="$status_code"
}

detect_scheduler_mode_from_json() {
  SCHEDULER_MODE="$("${LOBSTER_ROOT}/.venv/bin/python" -c "import json,sys; print(json.loads(sys.argv[1]).get('scheduler_mode','none'))" "$STATUS_JSON")"
}

plan_actions() {
  PLANNED_ACTIONS="$("${LOBSTER_ROOT}/.venv/bin/python" "${LOBSTER_ROOT}/scripts/recover_actions.py" "$STATUS_JSON" 2>/dev/null || true)"
}

plan_deep_actions() {
  PLANNED_DEEP_ACTIONS="$("${LOBSTER_ROOT}/.venv/bin/python" -c "
import json, sys
sys.path.insert(0, '${LOBSTER_ROOT}/scripts')
from recover_actions import plan_deep_recovery_actions
status = json.loads(sys.argv[1])
for action in plan_deep_recovery_actions(status, tier1_ran=True, still_degraded=True):
    print(action)
" "$STATUS_JSON" 2>/dev/null || true)"
}

reload_serve_macos() {
  local agents="${HOME}/Library/LaunchAgents"
  local deploy="${LOBSTER_ROOT}/deploy/launchd"
  local serve_src="${deploy}/com.erik.lobster-price-monitor.serve.plist"
  local serve_plist="${agents}/com.erik.lobster-price-monitor.serve.plist"

  if [[ ! -f "$serve_src" ]]; then
    echo "ERROR: serve plist not found at $serve_src" >&2
    return 1
  fi

  run mkdir -p "$agents"
  substitute_unit "$serve_src" "$serve_plist"
  if [[ "$DRY_RUN" != true ]] && launchctl list 2>/dev/null | grep -q "${SERVE_LABEL}$"; then
    run launchctl unload "$serve_plist" || true
  elif [[ "$DRY_RUN" == true ]]; then
    echo "[dry-run] launchctl unload $serve_plist (if loaded)"
  fi
  run launchctl load "$serve_plist"
}

reload_serve_linux() {
  local deploy="${LOBSTER_ROOT}/deploy/systemd"
  local src="${deploy}/lobster-price-monitor-serve.service"
  if [[ ! -f "$src" ]]; then
    echo "ERROR: serve unit not found at $src" >&2
    return 1
  fi
  install_linux_unit "$src"
  run sudo systemctl daemon-reload
  run sudo systemctl enable --now lobster-price-monitor-serve.service
}

do_reload_serve() {
  log "--- Recovery: reload serve ---"
  record_action "reload serve unit"
  case "$(uname -s)" in
    Darwin) reload_serve_macos ;;
    Linux) reload_serve_linux ;;
    *)
      log "WARNING: unknown OS — skipping serve reload"
      ;;
  esac
}

reload_ops_scrape_macos() {
  local agents="${HOME}/Library/LaunchAgents"
  local ops_src="${LOBSTER_ROOT}/deploy/launchd/com.erik.lobster-price-monitor.scrape.ops.plist"
  local ops_plist="${agents}/com.erik.lobster-price-monitor.scrape.ops.plist"

  run mkdir -p "$agents"
  substitute_unit "$ops_src" "$ops_plist"
  if [[ "$DRY_RUN" != true ]] && launchctl list 2>/dev/null | grep -q "${OPS_SCRAPE_LABEL}$"; then
    run launchctl unload "$ops_plist" || true
  elif [[ "$DRY_RUN" == true ]]; then
    echo "[dry-run] launchctl unload $ops_plist (if loaded)"
  fi
  run launchctl load "$ops_plist"
}

reload_dry_run_scrape_macos() {
  local agents="${HOME}/Library/LaunchAgents"
  local dry_src="${LOBSTER_ROOT}/deploy/launchd/com.erik.lobster-price-monitor.scrape.plist"
  local dry_plist="${agents}/com.erik.lobster-price-monitor.scrape.plist"

  run mkdir -p "$agents"
  substitute_unit "$dry_src" "$dry_plist"
  if [[ "$DRY_RUN" != true ]] && launchctl list 2>/dev/null | grep -q "${DRY_RUN_SCRAPE_LABEL}$"; then
    run launchctl unload "$dry_plist" || true
  elif [[ "$DRY_RUN" == true ]]; then
    echo "[dry-run] launchctl unload $dry_plist (if loaded)"
  fi
  run launchctl load "$dry_plist"
}

reload_ops_scrape_linux() {
  local deploy="${LOBSTER_ROOT}/deploy/systemd"
  for src in \
    "${deploy}/lobster-price-monitor-scrape.ops.service" \
    "${deploy}/lobster-price-monitor-scrape.ops.timer"; do
    install_linux_unit "$src"
  done
  run sudo systemctl daemon-reload
  run sudo systemctl enable --now "$OPS_SCRAPE_TIMER"
}

reload_dry_run_scrape_linux() {
  local deploy="${LOBSTER_ROOT}/deploy/systemd"
  for src in \
    "${deploy}/lobster-price-monitor-scrape.service" \
    "${deploy}/lobster-price-monitor-scrape.timer"; do
    install_linux_unit "$src"
  done
  run sudo systemctl daemon-reload
  run sudo systemctl enable --now "$DRY_RUN_SCRAPE_TIMER"
}

do_reload_scrape_scheduler() {
  log "--- Recovery: reload scrape scheduler ---"
  record_action "reload scrape scheduler"
  detect_scheduler_mode_from_json
  case "$SCHEDULER_MODE" in
    ops)
      case "$(uname -s)" in
        Darwin) reload_ops_scrape_macos ;;
        Linux) reload_ops_scrape_linux ;;
      esac
      ;;
    dry-run)
      case "$(uname -s)" in
        Darwin) reload_dry_run_scrape_macos ;;
        Linux) reload_dry_run_scrape_linux ;;
      esac
      ;;
    *)
      log "WARNING: scheduler mode ${SCHEDULER_MODE} — skipping scrape reload"
      ;;
  esac
}

do_trigger_scrape() {
  log "--- Recovery: confirmation scrape ---"
  record_action "run confirmation scrape"
  detect_scheduler_mode_from_json
  case "$SCHEDULER_MODE" in
    ops)
      run env LOBSTER_ALERTS=1 "${LOBSTER_ROOT}/scripts/run_scrape.sh"
      ;;
    *)
      run "${LOBSTER_ROOT}/.venv/bin/python" "${LOBSTER_ROOT}/scripts/scrape_markets.py" --no-alerts
      ;;
  esac
}

do_rerun_health() {
  log "--- Recovery: re-run health check ---"
  record_action "re-run health_check.py"
  if [[ "$DRY_RUN" == true ]]; then
    echo "[dry-run] ${LOBSTER_ROOT}/.venv/bin/python scripts/health_check.py"
    return 0
  fi
  "${LOBSTER_ROOT}/.venv/bin/python" "${LOBSTER_ROOT}/scripts/health_check.py" || true
}

do_install_watchdog() {
  log "--- Recovery: install watchdog timer ---"
  record_action "install watchdog timer"
  local flags=(--with-watchdog --watchdog-only --skip-verify --lobster-root "$LOBSTER_ROOT")
  [[ "$DRY_RUN" == true ]] && flags+=(--dry-run)
  bash "${LOBSTER_ROOT}/scripts/install_scheduler.sh" "${flags[@]}"
}

do_upgrade_host() {
  log "--- Recovery: deep upgrade (refresh deps + reload schedulers) ---"
  record_action "run upgrade_host (deep recovery)"
  DEEP_RECOVERY_ATTEMPTED=true
  local flags=(--skip-pull --skip-health --lobster-root "$LOBSTER_ROOT")
  [[ "$DRY_RUN" == true ]] && flags+=(--dry-run)
  bash "${LOBSTER_ROOT}/scripts/upgrade_host.sh" "${flags[@]}"
}

execute_action() {
  local action="$1"
  case "$action" in
    reload_serve) do_reload_serve ;;
    reload_scrape_scheduler) do_reload_scrape_scheduler ;;
    trigger_scrape) do_trigger_scrape ;;
    rerun_health) do_rerun_health ;;
    install_watchdog) do_install_watchdog ;;
    upgrade_host) do_upgrade_host ;;
    *)
      log "WARNING: unknown recovery action: $action"
      ;;
  esac
}

run_planned_actions() {
  local actions="$1"
  local label="${2:-recovery}"
  if [[ -z "${actions// }" ]]; then
    return 0
  fi
  log "Planned ${label} actions:"
  while IFS= read -r action; do
    [[ -z "$action" ]] && continue
    local action_label
    action_label="$("${LOBSTER_ROOT}/.venv/bin/python" -c "import sys; sys.path.insert(0, '${LOBSTER_ROOT}/scripts'); from recover_actions import action_labels; print(action_labels('${action}'))")"
    log "  - ${action_label}"
    execute_action "$action"
  done <<< "$actions"
}

maybe_notify() {
  local before_json="$1"
  local before_code="$2"
  local after_json="$3"
  local after_code="$4"

  if [[ "$NOTIFY" != true ]]; then
    return 0
  fi
  if [[ ${#ACTIONS_TAKEN[@]} -eq 0 ]]; then
    return 0
  fi

  if [[ "$DRY_RUN" != true ]]; then
    if ! bash "${LOBSTER_ROOT}/scripts/preflight_secrets.sh" --require-telegram >/dev/null 2>&1; then
      echo "ERROR: --notify requires Telegram secrets (preflight failed)" >&2
      return 1
    fi
  else
    log "[dry-run] bash scripts/preflight_secrets.sh --require-telegram"
  fi

  local alert_flags=(
    --recovery
    --status-json "$before_json"
    --status-json-after "$after_json"
    --exit-code-before "$before_code"
    --exit-code-after "$after_code"
    --actions-taken "${ACTIONS_TAKEN[@]}"
  )
  [[ "$FORCE" == true ]] && alert_flags+=(--force)
  [[ "$DRY_RUN" == true ]] && alert_flags+=(--dry-run)

  "${LOBSTER_ROOT}/.venv/bin/python" "${LOBSTER_ROOT}/scripts/watchdog_alert.py" "${alert_flags[@]}"
}

main() {
  log "=== Gate D Wave 12 host recovery ==="
  log "LOBSTER_ROOT=${LOBSTER_ROOT}"
  if [[ "$DEEP" == true ]]; then
    log "Deep recovery enabled"
  fi

  if [[ ! -x "${LOBSTER_ROOT}/.venv/bin/python" && "$DRY_RUN" != true ]]; then
    echo "ERROR: venv not found at ${LOBSTER_ROOT}/.venv — run scripts/bootstrap_host.sh first" >&2
    exit 2
  fi

  run_status
  local before_json="$STATUS_JSON"
  local before_code="$STATUS_CODE"

  if [[ "$before_code" -eq 0 ]]; then
    log "Host healthy — no recovery needed"
    if [[ "$DRY_RUN" == true ]]; then
      log "=== Recovery dry-run complete (exit 0) ==="
    else
      log "=== Recovery: HEALTHY ==="
    fi
    exit 0
  fi

  if [[ "$before_code" -ge 2 ]]; then
    log "Fatal preflight error — no auto-recovery"
    if [[ "$DRY_RUN" == true ]]; then
      log "=== Recovery dry-run complete (exit 0) ==="
      exit 0
    fi
    exit 2
  fi

  plan_actions
  if [[ -z "${PLANNED_ACTIONS// }" ]]; then
    log "No automated recovery actions for current degraded state"
    if [[ "$DRY_RUN" == true ]]; then
      log "=== Recovery dry-run complete (exit 0) ==="
      exit 0
    fi
    exit 1
  fi

  run_planned_actions "$PLANNED_ACTIONS" "tier-1 recovery"

  run_status
  local after_json="$STATUS_JSON"
  local after_code="$STATUS_CODE"

  if [[ "$after_code" -eq 1 && "$DEEP" == true ]]; then
    plan_deep_actions
    if [[ -n "${PLANNED_DEEP_ACTIONS// }" ]]; then
      log "--- Tier-2 deep recovery ---"
      run_planned_actions "$PLANNED_DEEP_ACTIONS" "tier-2 deep recovery"
      run_status
      after_json="$STATUS_JSON"
      after_code="$STATUS_CODE"
    fi
  fi

  maybe_notify "$before_json" "$before_code" "$after_json" "$after_code" || true

  if [[ "$DRY_RUN" == true ]]; then
    log "=== Recovery dry-run complete (exit 0) ==="
    exit 0
  fi

  if [[ "$after_code" -eq 0 ]]; then
    log "=== Recovery: HEALTHY ==="
  elif [[ "$after_code" -eq 1 ]]; then
    log "=== Recovery: STILL DEGRADED ==="
  else
    log "=== Recovery: FATAL ==="
  fi

  exit "$after_code"
}

main
