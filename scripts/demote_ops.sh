#!/usr/bin/env bash
# Roll back Gate D ops promotion to dry-run scheduler (no live Telegram alerts).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOBSTER_ROOT="${LOBSTER_ROOT:-$ROOT}"
DRY_RUN=false

usage() {
  cat <<'EOF'
Usage: scripts/demote_ops.sh [--dry-run] [--lobster-root PATH]

Demote host scheduler from ops back to dry-run:
  1. Preflight venv
  2. Unload/disable ops scrape scheduler
  3. Load/enable dry-run scrape scheduler
  4. Run one confirmation scrape with --no-alerts
  5. Run make verify-deploy

Set LOBSTER_ROOT to override install path (default: repo root).
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=true
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

substitute_unit() {
  local src="$1"
  local dest="$2"
  if [[ "$DRY_RUN" == true ]]; then
    echo "[dry-run] sed 's|LOBSTER_ROOT|${LOBSTER_ROOT}|g' $src > $dest"
  else
    sed "s|LOBSTER_ROOT|${LOBSTER_ROOT}|g" "$src" > "$dest"
  fi
}

preflight() {
  if [[ ! -x "${LOBSTER_ROOT}/.venv/bin/python" ]]; then
    echo "ERROR: venv not found at ${LOBSTER_ROOT}/.venv — run scripts/install.sh first" >&2
    exit 1
  fi
  echo "Preflight OK (LOBSTER_ROOT=$LOBSTER_ROOT)"
}

demote_macos() {
  local agents="${HOME}/Library/LaunchAgents"
  local dry_src="${LOBSTER_ROOT}/deploy/launchd/com.erik.lobster-price-monitor.scrape.plist"
  local ops_plist="${agents}/com.erik.lobster-price-monitor.scrape.ops.plist"
  local dry_plist="${agents}/com.erik.lobster-price-monitor.scrape.plist"

  if [[ ! -f "$dry_src" ]]; then
    echo "ERROR: dry-run plist template not found at $dry_src" >&2
    exit 1
  fi

  run mkdir -p "$agents"

  if [[ -f "$ops_plist" ]]; then
    if launchctl list 2>/dev/null | grep -q "com.erik.lobster-price-monitor.scrape.ops$"; then
      run launchctl unload "$ops_plist"
    else
      echo "Ops plist present but not loaded — skipping unload"
    fi
  else
    echo "No ops plist at $ops_plist — skipping unload"
  fi

  substitute_unit "$dry_src" "$dry_plist"
  run launchctl load "$dry_plist"
  echo "macOS demotion complete: $dry_plist"
}

install_linux_unit() {
  local src="$1"
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
}

demote_linux() {
  local deploy="${LOBSTER_ROOT}/deploy/systemd"
  local dry_service="${deploy}/lobster-price-monitor-scrape.service"
  local dry_timer="${deploy}/lobster-price-monitor-scrape.timer"

  for src in "$dry_service" "$dry_timer"; do
    if [[ ! -f "$src" ]]; then
      echo "ERROR: dry-run unit not found at $src" >&2
      exit 1
    fi
    install_linux_unit "$src"
  done

  run sudo systemctl daemon-reload
  run sudo systemctl disable --now lobster-price-monitor-scrape.ops.timer || true
  run sudo systemctl enable --now lobster-price-monitor-scrape.timer
  echo "Linux demotion complete: lobster-price-monitor-scrape.timer"
}

confirm_scrape() {
  run "${LOBSTER_ROOT}/.venv/bin/python" "${LOBSTER_ROOT}/scripts/scrape_markets.py" --no-alerts
}

verify_deploy() {
  if [[ "$DRY_RUN" == true ]]; then
    echo "[dry-run] make -C ${LOBSTER_ROOT} verify-deploy"
    return 0
  fi
  make -C "$LOBSTER_ROOT" verify-deploy
}

main() {
  echo "=== Gate D ops demotion (rollback to dry-run) ==="
  preflight

  case "$(uname -s)" in
    Darwin)
      demote_macos
      ;;
    Linux)
      demote_linux
      ;;
    *)
      echo "ERROR: demote_ops.sh supports macOS and Linux only (got $(uname -s))" >&2
      exit 1
      ;;
  esac

  confirm_scrape
  verify_deploy
  echo "=== Ops demotion succeeded ==="
}

main
