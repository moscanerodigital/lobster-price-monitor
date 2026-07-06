#!/usr/bin/env bash
# Install dry-run scrape + serve schedulers (Gate D Wave 4 / NEXT_AGENT Phase 2).
# macOS: launchd plists. Linux: systemd units with LOBSTER_ROOT substitution.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOBSTER_ROOT="${LOBSTER_ROOT:-$ROOT}"
DRY_RUN=false
SKIP_HEALTH=false
SKIP_VERIFY=false
WITH_WATCHDOG=false
WATCHDOG_ONLY=false

usage() {
  cat <<'EOF'
Usage: scripts/install_scheduler.sh [--dry-run] [--skip-health] [--skip-verify] [--with-watchdog] [--watchdog-only]

Install dry-run scrape + serve schedulers (no Telegram alerts):
  1. Preflight venv and LOBSTER_ROOT
  2. Install scrape + serve units (launchd or systemd)
  3. Optionally install daily health-log unit
  4. Optionally install watchdog timer (--with-watchdog)
  5. Run make verify-deploy (host)

With --watchdog-only, install only the watchdog timer (requires --with-watchdog).

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
    --skip-verify)
      SKIP_VERIFY=true
      shift
      ;;
    --with-watchdog)
      WITH_WATCHDOG=true
      shift
      ;;
    --watchdog-only)
      WATCHDOG_ONLY=true
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
  if [[ ! -w "$LOBSTER_ROOT" ]]; then
    echo "ERROR: LOBSTER_ROOT is not writable: $LOBSTER_ROOT" >&2
    exit 1
  fi
  mkdir -p "${LOBSTER_ROOT}/logs"
  echo "Preflight OK (LOBSTER_ROOT=$LOBSTER_ROOT)"
}

install_macos() {
  local agents="${HOME}/Library/LaunchAgents"
  local deploy="${LOBSTER_ROOT}/deploy/launchd"
  local scrape_src="${deploy}/com.erik.lobster-price-monitor.scrape.plist"
  local serve_src="${deploy}/com.erik.lobster-price-monitor.serve.plist"
  local health_src="${deploy}/com.erik.lobster-price-monitor.health.plist"
  local scrape_plist="${agents}/com.erik.lobster-price-monitor.scrape.plist"
  local serve_plist="${agents}/com.erik.lobster-price-monitor.serve.plist"
  local health_plist="${agents}/com.erik.lobster-price-monitor.health.plist"

  for src in "$scrape_src" "$serve_src"; do
    if [[ ! -f "$src" ]]; then
      echo "ERROR: unit template not found at $src" >&2
      exit 1
    fi
  done

  run mkdir -p "$agents"
  substitute_unit "$scrape_src" "$scrape_plist"
  substitute_unit "$serve_src" "$serve_plist"

  if launchctl list 2>/dev/null | grep -q "com.erik.lobster-price-monitor.scrape.ops$"; then
    echo "WARNING: ops scrape agent already loaded — skipping dry-run scrape install"
  else
    if launchctl list 2>/dev/null | grep -q "com.erik.lobster-price-monitor.scrape$"; then
      run launchctl unload "$scrape_plist" || true
    fi
    run launchctl load "$scrape_plist"
  fi

  if launchctl list 2>/dev/null | grep -q "com.erik.lobster-price-monitor.serve$"; then
    run launchctl unload "$serve_plist" || true
  fi
  run launchctl load "$serve_plist"

  if [[ "$SKIP_HEALTH" == false ]]; then
    if [[ ! -f "$health_src" ]]; then
      echo "ERROR: health plist not found at $health_src" >&2
      exit 1
    fi
    substitute_unit "$health_src" "$health_plist"
    if launchctl list 2>/dev/null | grep -q "com.erik.lobster-price-monitor.health$"; then
      run launchctl unload "$health_plist" || true
    fi
    run launchctl load "$health_plist"
    echo "macOS health agent installed: $health_plist"
  fi

  echo "macOS scheduler install complete (scrape + serve)"
}

install_watchdog_macos() {
  local agents="${HOME}/Library/LaunchAgents"
  local deploy="${LOBSTER_ROOT}/deploy/launchd"
  local watchdog_src="${deploy}/com.erik.lobster-price-monitor.watchdog.plist"
  local watchdog_plist="${agents}/com.erik.lobster-price-monitor.watchdog.plist"

  if [[ ! -f "$watchdog_src" ]]; then
    echo "ERROR: watchdog plist not found at $watchdog_src" >&2
    exit 1
  fi

  run mkdir -p "$agents"
  substitute_unit "$watchdog_src" "$watchdog_plist"
  if launchctl list 2>/dev/null | grep -q "com.erik.lobster-price-monitor.watchdog$"; then
    run launchctl unload "$watchdog_plist" || true
  fi
  run launchctl load "$watchdog_plist"
  echo "macOS watchdog agent installed: $watchdog_plist"
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

install_linux() {
  local deploy="${LOBSTER_ROOT}/deploy/systemd"
  local units=(
    "${deploy}/lobster-price-monitor-scrape.service"
    "${deploy}/lobster-price-monitor-scrape.timer"
    "${deploy}/lobster-price-monitor-serve.service"
  )

  for src in "${units[@]}"; do
    if [[ ! -f "$src" ]]; then
      echo "ERROR: unit template not found at $src" >&2
      exit 1
    fi
    install_linux_unit "$src"
  done

  if [[ "$SKIP_HEALTH" == false ]]; then
    for src in \
      "${deploy}/lobster-price-monitor-health.service" \
      "${deploy}/lobster-price-monitor-health.timer"; do
      if [[ ! -f "$src" ]]; then
        echo "ERROR: health unit not found at $src" >&2
        exit 1
      fi
      install_linux_unit "$src"
    done
  fi

  run sudo systemctl daemon-reload

  if systemctl is-enabled lobster-price-monitor-scrape.ops.timer &>/dev/null; then
    echo "WARNING: ops scrape timer already enabled — skipping dry-run scrape timer"
  else
    run sudo systemctl enable --now lobster-price-monitor-scrape.timer
  fi

  run sudo systemctl enable --now lobster-price-monitor-serve.service

  if [[ "$SKIP_HEALTH" == false ]]; then
    run sudo systemctl enable --now lobster-price-monitor-health.timer
    echo "Linux health timer enabled: lobster-price-monitor-health.timer"
  fi

  echo "Linux scheduler install complete (scrape + serve)"
}

install_watchdog_linux() {
  local deploy="${LOBSTER_ROOT}/deploy/systemd"
  for src in \
    "${deploy}/lobster-price-monitor-watchdog.service" \
    "${deploy}/lobster-price-monitor-watchdog.timer"; do
    if [[ ! -f "$src" ]]; then
      echo "ERROR: watchdog unit not found at $src" >&2
      exit 1
    fi
    install_linux_unit "$src"
  done

  run sudo systemctl daemon-reload
  run sudo systemctl enable --now lobster-price-monitor-watchdog.timer
  echo "Linux watchdog timer enabled: lobster-price-monitor-watchdog.timer"
}

verify_deploy() {
  if [[ "$SKIP_VERIFY" == true ]]; then
    echo "Skipping verify-deploy"
    return 0
  fi
  if [[ "$DRY_RUN" == true ]]; then
    echo "[dry-run] make -C ${LOBSTER_ROOT} verify-deploy"
    return 0
  fi
  make -C "$LOBSTER_ROOT" verify-deploy
}

main() {
  if [[ "$WATCHDOG_ONLY" == true && "$WITH_WATCHDOG" != true ]]; then
    echo "ERROR: --watchdog-only requires --with-watchdog" >&2
    exit 1
  fi

  if [[ "$WATCHDOG_ONLY" == true ]]; then
    echo "=== Gate D watchdog install ==="
    preflight
    case "$(uname -s)" in
      Darwin)
        install_watchdog_macos
        ;;
      Linux)
        install_watchdog_linux
        ;;
      *)
        echo "ERROR: install_scheduler.sh supports macOS and Linux only (got $(uname -s))" >&2
        exit 1
        ;;
    esac
    echo "=== Watchdog install succeeded ==="
    return 0
  fi

  echo "=== Gate D scheduler install (dry-run scrape + serve) ==="
  preflight

  case "$(uname -s)" in
    Darwin)
      install_macos
      ;;
    Linux)
      install_linux
      ;;
    *)
      echo "ERROR: install_scheduler.sh supports macOS and Linux only (got $(uname -s))" >&2
      exit 1
      ;;
  esac

  if [[ "$WITH_WATCHDOG" == true ]]; then
    case "$(uname -s)" in
      Darwin)
        install_watchdog_macos
        ;;
      Linux)
        install_watchdog_linux
        ;;
    esac
  fi

  verify_deploy
  echo "=== Scheduler install succeeded ==="
}

main
