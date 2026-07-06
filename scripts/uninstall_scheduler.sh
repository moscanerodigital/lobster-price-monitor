#!/usr/bin/env bash
# Uninstall lobster-price-monitor schedulers (Gate D Wave 6).
# macOS: launchd unload. Linux: systemd disable --now.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOBSTER_ROOT="${LOBSTER_ROOT:-$ROOT}"
DRY_RUN=false
SKIP_HEALTH=false
PURGE_FILES=false

DRY_RUN_SCRAPE_LABEL="com.erik.lobster-price-monitor.scrape"
OPS_SCRAPE_LABEL="com.erik.lobster-price-monitor.scrape.ops"
SERVE_LABEL="com.erik.lobster-price-monitor.serve"
HEALTH_LABEL="com.erik.lobster-price-monitor.health"
DRY_RUN_SCRAPE_TIMER="lobster-price-monitor-scrape.timer"
OPS_SCRAPE_TIMER="lobster-price-monitor-scrape.ops.timer"
SERVE_SERVICE="lobster-price-monitor-serve.service"
HEALTH_TIMER="lobster-price-monitor-health.timer"

usage() {
  cat <<'EOF'
Usage: scripts/uninstall_scheduler.sh [--dry-run] [--skip-health] [--purge-files] [--lobster-root PATH]

Unload/disable all lobster-price-monitor schedulers:
  - dry-run scrape + ops scrape
  - board serve
  - daily health log (unless --skip-health)

With --purge-files, remove installed plists/units from the host after unload.

Set LOBSTER_ROOT to override install path (default: repo root).
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    --skip-health)
      SKIP_HEALTH=true
      shift
      ;;
    --purge-files)
      PURGE_FILES=true
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

unload_macos_plist() {
  local label="$1"
  local plist="${HOME}/Library/LaunchAgents/${label}.plist"

  if launchctl list 2>/dev/null | grep -q "${label}$"; then
    if [[ -f "$plist" ]]; then
      run launchctl unload "$plist" || true
    else
      run launchctl bootout "gui/$(id -u)/${label}" 2>/dev/null || \
        run launchctl unload "$label" 2>/dev/null || true
    fi
    echo "  unloaded ${label}"
  else
    echo "  ${label} not loaded — skipping"
  fi

  if [[ "$PURGE_FILES" == true && -f "$plist" ]]; then
    run rm -f "$plist"
    echo "  purged ${plist}"
  fi
}

uninstall_macos() {
  local agents="${HOME}/Library/LaunchAgents"

  echo "macOS: unloading launchd agents"
  unload_macos_plist "$OPS_SCRAPE_LABEL"
  unload_macos_plist "$DRY_RUN_SCRAPE_LABEL"
  unload_macos_plist "$SERVE_LABEL"
  if [[ "$SKIP_HEALTH" == false ]]; then
    unload_macos_plist "$HEALTH_LABEL"
  else
    echo "  skipping health agent (--skip-health)"
  fi

  echo "macOS scheduler uninstall complete"
}

disable_linux_unit() {
  local unit="$1"
  if systemctl list-unit-files "$unit" &>/dev/null; then
    if systemctl is-enabled "$unit" &>/dev/null; then
      run sudo systemctl disable --now "$unit" || true
      echo "  disabled ${unit}"
    else
      echo "  ${unit} not enabled — skipping disable"
    fi
  else
    echo "  ${unit} not installed — skipping"
  fi

  if [[ "$PURGE_FILES" == true ]]; then
    local unit_path="/etc/systemd/system/${unit}"
    if [[ -f "$unit_path" ]]; then
      run sudo rm -f "$unit_path"
      echo "  purged ${unit_path}"
    fi
  fi
}

uninstall_linux() {
  echo "Linux: disabling systemd units"
  disable_linux_unit "$OPS_SCRAPE_TIMER"
  disable_linux_unit "$DRY_RUN_SCRAPE_TIMER"
  disable_linux_unit "$SERVE_SERVICE"
  if [[ "$SKIP_HEALTH" == false ]]; then
    disable_linux_unit "$HEALTH_TIMER"
  else
    echo "  skipping health timer (--skip-health)"
  fi

  if [[ "$PURGE_FILES" == true ]]; then
    for unit in \
      lobster-price-monitor-scrape.service \
      lobster-price-monitor-scrape.ops.service \
      lobster-price-monitor-health.service; do
      local unit_path="/etc/systemd/system/${unit}"
      if [[ -f "$unit_path" ]]; then
        run sudo rm -f "$unit_path"
        echo "  purged ${unit_path}"
      fi
    done
    run sudo systemctl daemon-reload
  fi

  echo "Linux scheduler uninstall complete"
}

post_check() {
  local failed=false

  case "$(uname -s)" in
    Darwin)
      local labels=("$OPS_SCRAPE_LABEL" "$DRY_RUN_SCRAPE_LABEL" "$SERVE_LABEL")
      if [[ "$SKIP_HEALTH" == false ]]; then
        labels+=("$HEALTH_LABEL")
      fi
      local loaded
      loaded="$(launchctl list 2>/dev/null || true)"
      for label in "${labels[@]}"; do
        if echo "$loaded" | grep -q "${label}$"; then
          echo "ERROR: post-check failed — ${label} still loaded" >&2
          failed=true
        fi
      done
      ;;
    Linux)
      local units=("$OPS_SCRAPE_TIMER" "$DRY_RUN_SCRAPE_TIMER" "$SERVE_SERVICE")
      if [[ "$SKIP_HEALTH" == false ]]; then
        units+=("$HEALTH_TIMER")
      fi
      for unit in "${units[@]}"; do
        if systemctl is-active "$unit" &>/dev/null; then
          echo "ERROR: post-check failed — ${unit} still active" >&2
          failed=true
        fi
      done
      ;;
    *)
      echo "  ! Unknown OS — skipping post-check"
      return 0
      ;;
  esac

  if [[ "$failed" == true ]]; then
    exit 1
  fi
  echo "  ✓ post-check: no lobster schedulers loaded"
}

main() {
  echo "=== Gate D scheduler uninstall ==="
  echo "LOBSTER_ROOT=$LOBSTER_ROOT"

  case "$(uname -s)" in
    Darwin)
      uninstall_macos
      ;;
    Linux)
      uninstall_linux
      ;;
    *)
      echo "ERROR: uninstall_scheduler.sh supports macOS and Linux only (got $(uname -s))" >&2
      exit 1
      ;;
  esac

  if [[ "$DRY_RUN" == true ]]; then
    echo "[dry-run] post-check: verify no schedulers loaded"
  else
    post_check
  fi

  echo "=== Scheduler uninstall succeeded ==="
}

main
