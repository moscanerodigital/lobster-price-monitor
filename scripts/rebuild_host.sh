#!/usr/bin/env bash
# Gate D Wave 14 host rebuild — fresh venv + bootstrap verify + scheduler redeploy.
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
Usage: scripts/rebuild_host.sh [--dry-run] [--skip-scrape] [--skip-verify] [--skip-health] [--lobster-root PATH]

Full host rebuild (tier-4 recovery — preserves data/ and scheduler mode):
  1. Preflight LOBSTER_ROOT and detect scheduler mode
  2. Remove .venv and run scripts/install.sh (fresh venv)
  3. scripts/dry_run.sh + verify-production-ci + verify-ops-ci + health_check.py
  4. redeploy_host.sh (uninstall + reinstall schedulers + re-promote ops)
  5. Optional confirmation scrape and gate verify

Does not delete data/, run git pull, or run full teardown.

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

run() {
  if [[ "$DRY_RUN" == true ]]; then
    echo "[dry-run] $*"
  else
    echo "+ $*"
    "$@"
  fi
}

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
  mkdir -p "${LOBSTER_ROOT}/logs" "${LOBSTER_ROOT}/data"
  bash "${LOBSTER_ROOT}/scripts/preflight_secrets.sh" $([[ "$DRY_RUN" == true ]] && echo --dry-run)
  echo "Preflight OK (LOBSTER_ROOT=$LOBSTER_ROOT)"
}

rebuild_venv() {
  echo "--- Rebuilding venv ---"
  if [[ "$DRY_RUN" == true ]]; then
    echo "[dry-run] rm -rf ${LOBSTER_ROOT}/.venv"
    echo "[dry-run] bash ${LOBSTER_ROOT}/scripts/install.sh"
    return 0
  fi
  rm -rf "${LOBSTER_ROOT}/.venv"
  bash "${LOBSTER_ROOT}/scripts/install.sh"
}

bootstrap_verify() {
  echo "--- Bootstrap verify path ---"
  run bash "${LOBSTER_ROOT}/scripts/dry_run.sh"
  if [[ "$SKIP_VERIFY" != true ]]; then
    run make -C "$LOBSTER_ROOT" verify-production-ci
    run make -C "$LOBSTER_ROOT" verify-ops-ci
  else
    echo "Skipping CI gate verify (--skip-verify)"
  fi
  if [[ "$SKIP_HEALTH" != true ]]; then
    run "${LOBSTER_ROOT}/.venv/bin/python" "${LOBSTER_ROOT}/scripts/health_check.py"
  else
    echo "Skipping health check (--skip-health)"
  fi
}

redeploy_schedulers() {
  echo "--- Scheduler redeploy (tier-3 within rebuild) ---"
  local flags=(--lobster-root "$LOBSTER_ROOT")
  [[ "$DRY_RUN" == true ]] && flags+=(--dry-run)
  [[ "$SKIP_SCRAPE" == true ]] && flags+=(--skip-scrape)
  [[ "$SKIP_VERIFY" == true ]] && flags+=(--skip-verify)
  [[ "$SKIP_HEALTH" == true ]] && flags+=(--skip-health)
  bash "${LOBSTER_ROOT}/scripts/redeploy_host.sh" "${flags[@]}"
}

main() {
  echo "=== Gate D Wave 14 host rebuild ==="

  preflight
  detect_scheduler_mode
  detect_watchdog_state
  rebuild_venv
  bootstrap_verify
  redeploy_schedulers

  echo "=== Host rebuild succeeded ==="
}

main
