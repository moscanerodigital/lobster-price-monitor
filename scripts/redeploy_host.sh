#!/usr/bin/env bash
# Gate D Wave 13 host redeploy — uninstall and reinstall schedulers (preserves data/ and mode).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOBSTER_ROOT="${LOBSTER_ROOT:-$ROOT}"
DRY_RUN=false
SKIP_SCRAPE=false
SKIP_VERIFY=false
SKIP_HEALTH=false

OPS_SCRAPE_LABEL="com.erik.lobster-price-monitor.scrape.ops"
DRY_RUN_SCRAPE_LABEL="com.erik.lobster-price-monitor.scrape"
OPS_SCRAPE_TIMER="lobster-price-monitor-scrape.ops.timer"
DRY_RUN_SCRAPE_TIMER="lobster-price-monitor-scrape.timer"
WATCHDOG_LABEL="com.erik.lobster-price-monitor.watchdog"
WATCHDOG_TIMER="lobster-price-monitor-watchdog.timer"
SAVED_MODE="none"
WATCHDOG_WAS_LOADED=false

usage() {
  cat <<'EOF'
Usage: scripts/redeploy_host.sh [--dry-run] [--skip-scrape] [--skip-verify] [--skip-health] [--lobster-root PATH]

Scheduler redeploy (tier-3 recovery — preserves data/ and scheduler mode):
  1. Preflight venv and LOBSTER_ROOT
  2. Detect scheduler mode and watchdog state
  3. uninstall_scheduler.sh (schedulers only — no data purge)
  4. install_scheduler.sh (--with-watchdog when ops or watchdog was loaded)
  5. promote_ops.sh when prior mode was ops
  6. Optional confirmation scrape
  7. make verify-deploy (dry-run) or make verify-ops (ops)

Does not delete data/, .venv/, or the repo clone.

Set LOBSTER_ROOT to override install path (default: repo root).
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    --skip-scrape)
      SKIP_SCRAPE=true
      shift
      ;;
    --skip-verify)
      SKIP_VERIFY=true
      shift
      ;;
    --skip-health)
      SKIP_HEALTH=true
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

dry_flag() {
  [[ "$DRY_RUN" == true ]] && echo --dry-run
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

watchdog_loaded() {
  case "$(uname -s)" in
    Darwin)
      launchctl list 2>/dev/null | grep -q "${WATCHDOG_LABEL}$"
      ;;
    Linux)
      systemctl is-enabled "$WATCHDOG_TIMER" &>/dev/null
      ;;
    *)
      return 1
      ;;
  esac
}

detect_scheduler_mode() {
  if ops_loaded; then
    SAVED_MODE="ops"
  elif dry_run_loaded; then
    SAVED_MODE="dry-run"
  else
    SAVED_MODE="none"
  fi
  echo "Saved scheduler mode: ${SAVED_MODE}"
}

detect_watchdog_state() {
  if watchdog_loaded; then
    WATCHDOG_WAS_LOADED=true
    echo "Watchdog was loaded: yes"
  else
    WATCHDOG_WAS_LOADED=false
    echo "Watchdog was loaded: no"
  fi
}

preflight() {
  if [[ ! -w "$LOBSTER_ROOT" ]]; then
    echo "ERROR: LOBSTER_ROOT is not writable: $LOBSTER_ROOT" >&2
    exit 1
  fi
  if [[ ! -x "${LOBSTER_ROOT}/.venv/bin/python" ]]; then
    echo "ERROR: venv not found at ${LOBSTER_ROOT}/.venv — run scripts/bootstrap_host.sh first" >&2
    exit 1
  fi
  mkdir -p "${LOBSTER_ROOT}/logs"
  echo "Preflight OK (LOBSTER_ROOT=$LOBSTER_ROOT)"
}

uninstall_schedulers() {
  echo "--- Uninstalling schedulers ---"
  local flags=(--lobster-root "$LOBSTER_ROOT")
  [[ "$DRY_RUN" == true ]] && flags+=(--dry-run)
  [[ "$SKIP_HEALTH" == true ]] && flags+=(--skip-health)
  bash "${LOBSTER_ROOT}/scripts/uninstall_scheduler.sh" "${flags[@]}"
}

reinstall_schedulers() {
  echo "--- Reinstalling schedulers ---"
  local flags=(--lobster-root "$LOBSTER_ROOT" --skip-verify)
  [[ "$DRY_RUN" == true ]] && flags+=(--dry-run)
  [[ "$SKIP_HEALTH" == true ]] && flags+=(--skip-health)
  if [[ "$SAVED_MODE" == "ops" || "$WATCHDOG_WAS_LOADED" == true ]]; then
    flags+=(--with-watchdog)
  fi
  bash "${LOBSTER_ROOT}/scripts/install_scheduler.sh" "${flags[@]}"
}

maybe_promote_ops() {
  if [[ "$SAVED_MODE" != "ops" ]]; then
    return 0
  fi

  echo "--- Re-promoting ops scheduler ---"
  bash "${LOBSTER_ROOT}/scripts/promote_ops.sh" $(dry_flag)
}

confirm_scrape() {
  if [[ "$SKIP_SCRAPE" == true ]]; then
    echo "Skipping confirmation scrape (--skip-scrape)"
    return 0
  fi

  echo "--- Confirmation scrape ---"
  if [[ "$DRY_RUN" == true ]]; then
    if [[ "$SAVED_MODE" == "ops" ]]; then
      echo "[dry-run] env LOBSTER_ALERTS=1 ${LOBSTER_ROOT}/scripts/run_scrape.sh"
    else
      echo "[dry-run] ${LOBSTER_ROOT}/.venv/bin/python scripts/scrape_markets.py --no-alerts"
    fi
    return 0
  fi

  case "$SAVED_MODE" in
    ops)
      env LOBSTER_ALERTS=1 "${LOBSTER_ROOT}/scripts/run_scrape.sh"
      ;;
    *)
      "${LOBSTER_ROOT}/.venv/bin/python" "${LOBSTER_ROOT}/scripts/scrape_markets.py" --no-alerts
      ;;
  esac
}

run_verify() {
  if [[ "$SKIP_VERIFY" == true ]]; then
    echo "Skipping gate verify (--skip-verify)"
    return 0
  fi

  echo "--- Gate verification ---"
  if [[ "$DRY_RUN" == true ]]; then
    if [[ "$SAVED_MODE" == "ops" ]]; then
      echo "[dry-run] make -C ${LOBSTER_ROOT} verify-ops"
    elif [[ "$SAVED_MODE" == "dry-run" ]]; then
      echo "[dry-run] make -C ${LOBSTER_ROOT} verify-deploy"
    else
      echo "[dry-run] make -C ${LOBSTER_ROOT} verify-production-ci"
    fi
    return 0
  fi

  case "$SAVED_MODE" in
    ops)
      make -C "$LOBSTER_ROOT" verify-ops
      ;;
    dry-run)
      make -C "$LOBSTER_ROOT" verify-deploy
      ;;
    none)
      make -C "$LOBSTER_ROOT" verify-production-ci
      ;;
  esac
}

main() {
  echo "=== Gate D Wave 13 host redeploy ==="

  preflight
  detect_scheduler_mode
  detect_watchdog_state
  uninstall_schedulers
  reinstall_schedulers
  maybe_promote_ops
  confirm_scrape
  run_verify

  echo "=== Host redeploy succeeded ==="
}

main
