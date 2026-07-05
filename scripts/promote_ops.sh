#!/usr/bin/env bash
# Promote lobster-price-monitor from dry-run scheduler to Gate D ops (live alerts).
# macOS: swap launchd scrape → scrape.ops. Linux: swap systemd scrape timer → ops timer.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOBSTER_ROOT="${LOBSTER_ROOT:-$ROOT}"
DRY_RUN=false

usage() {
  cat <<'EOF'
Usage: scripts/promote_ops.sh [--dry-run]

Promote host scheduler to Gate D ops (LOBSTER_ALERTS=1):
  1. Preflight secrets and venv
  2. Unload/disable dry-run scrape scheduler
  3. Load/enable ops scrape scheduler
  4. Run one confirmation scrape with alerts
  5. Run make verify-ops

Set LOBSTER_ROOT to override install path (default: repo root).
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=true
      shift
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

preflight() {
  local token="${HOME}/.openclaw/secrets/telegram/herb.token"
  if [[ ! -f "$token" ]]; then
    if [[ "$DRY_RUN" == true ]]; then
      echo "WARNING: Telegram token missing at $token (required for real promotion)"
    else
      echo "ERROR: Telegram token missing at $token" >&2
      echo "Save Erik's bot token before promoting to ops alerts." >&2
      exit 1
    fi
  fi
  if [[ ! -x "${LOBSTER_ROOT}/.venv/bin/python" ]]; then
    echo "ERROR: venv not found at ${LOBSTER_ROOT}/.venv — run scripts/install.sh first" >&2
    exit 1
  fi
  echo "Preflight OK (LOBSTER_ROOT=$LOBSTER_ROOT)"
}

promote_macos() {
  local agents="${HOME}/Library/LaunchAgents"
  local dry_plist="${agents}/com.erik.lobster-price-monitor.scrape.plist"
  local ops_src="${LOBSTER_ROOT}/deploy/launchd/com.erik.lobster-price-monitor.scrape.ops.plist"
  local ops_plist="${agents}/com.erik.lobster-price-monitor.scrape.ops.plist"

  if [[ ! -f "$ops_src" ]]; then
    echo "ERROR: ops plist not found at $ops_src" >&2
    exit 1
  fi

  run mkdir -p "$agents"
  if [[ "$DRY_RUN" == true ]]; then
    echo "[dry-run] sed 's|LOBSTER_ROOT|${LOBSTER_ROOT}|g' $ops_src > $ops_plist"
  else
    sed "s|LOBSTER_ROOT|${LOBSTER_ROOT}|g" "$ops_src" > "$ops_plist"
  fi

  if [[ -f "$dry_plist" ]]; then
    if launchctl list 2>/dev/null | grep -q "com.erik.lobster-price-monitor.scrape$"; then
      run launchctl unload "$dry_plist"
    else
      echo "Dry-run plist present but not loaded — skipping unload"
    fi
  else
    echo "No dry-run plist at $dry_plist — skipping unload"
  fi

  run launchctl load "$ops_plist"
  echo "macOS ops promotion complete: $ops_plist"
}

promote_linux() {
  local deploy="${LOBSTER_ROOT}/deploy/systemd"
  local ops_service="${deploy}/lobster-price-monitor-scrape.ops.service"
  local ops_timer="${deploy}/lobster-price-monitor-scrape.ops.timer"

  for src in "$ops_service" "$ops_timer"; do
    if [[ ! -f "$src" ]]; then
      echo "ERROR: ops unit not found at $src" >&2
      exit 1
    fi
    local name
    name="$(basename "$src")"
    local tmp
    tmp="$(mktemp)"
    if [[ "$DRY_RUN" == true ]]; then
      echo "[dry-run] sed 's|LOBSTER_ROOT|${LOBSTER_ROOT}|g' $src > /etc/systemd/system/$name"
      rm -f "$tmp"
    else
      sed "s|LOBSTER_ROOT|${LOBSTER_ROOT}|g" "$src" > "$tmp"
      sudo cp "$tmp" "/etc/systemd/system/$name"
      rm -f "$tmp"
    fi
  done

  run sudo systemctl daemon-reload
  run sudo systemctl disable --now lobster-price-monitor-scrape.timer || true
  run sudo systemctl enable --now lobster-price-monitor-scrape.ops.timer
  echo "Linux ops promotion complete: lobster-price-monitor-scrape.ops.timer"
}

confirm_scrape() {
  run env LOBSTER_ALERTS=1 "${LOBSTER_ROOT}/scripts/run_scrape.sh"
}

verify_ops() {
  if [[ "$DRY_RUN" == true ]]; then
    echo "[dry-run] make -C ${LOBSTER_ROOT} verify-ops"
    return 0
  fi
  make -C "$LOBSTER_ROOT" verify-ops
}

main() {
  echo "=== Gate D ops promotion ==="
  preflight

  case "$(uname -s)" in
    Darwin)
      promote_macos
      ;;
    Linux)
      promote_linux
      ;;
    *)
      echo "ERROR: promote_ops.sh supports macOS and Linux only (got $(uname -s))" >&2
      exit 1
      ;;
  esac

  confirm_scrape
  verify_ops
  echo "=== Ops promotion succeeded ==="
}

main
