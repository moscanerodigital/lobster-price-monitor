#!/usr/bin/env bash
# Gate D Wave 7 host upgrade — pull code, refresh deps, reload schedulers in place.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOBSTER_ROOT="${LOBSTER_ROOT:-$ROOT}"
DRY_RUN=false
SKIP_PULL=false
SKIP_SCRAPE=false
SKIP_VERIFY=false
SKIP_HEALTH=false

OPS_SCRAPE_LABEL="com.erik.lobster-price-monitor.scrape.ops"
DRY_RUN_SCRAPE_LABEL="com.erik.lobster-price-monitor.scrape"
OPS_SCRAPE_TIMER="lobster-price-monitor-scrape.ops.timer"
DRY_RUN_SCRAPE_TIMER="lobster-price-monitor-scrape.timer"
SCHEDULER_MODE="none"

usage() {
  cat <<'EOF'
Usage: scripts/upgrade_host.sh [--dry-run] [--skip-pull] [--skip-scrape] [--skip-verify] [--skip-health] [--lobster-root PATH]

In-place host upgrade (preserves data/ and scheduler mode):
  1. Preflight venv and LOBSTER_ROOT
  2. git pull --ff-only (unless --skip-pull)
  3. scripts/install.sh (refresh pip packages)
  4. Reload schedulers matching current mode (dry-run or ops)
  5. Optional confirmation scrape
  6. make verify-deploy (dry-run) or make verify-ops (ops)

Does not demote ops or promote dry-run. Does not delete data/.

Set LOBSTER_ROOT to override install path (default: repo root).
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    --skip-pull)
      SKIP_PULL=true
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

substitute_unit() {
  local src="$1"
  local dest="$2"
  if [[ "$DRY_RUN" == true ]]; then
    echo "[dry-run] sed 's|LOBSTER_ROOT|${LOBSTER_ROOT}|g' $src > $dest"
  else
    sed "s|LOBSTER_ROOT|${LOBSTER_ROOT}|g" "$src" > "$dest"
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
  echo "Scheduler mode: ${SCHEDULER_MODE}"
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

pull_code() {
  if [[ "$SKIP_PULL" == true ]]; then
    echo "Skipping git pull (--skip-pull)"
    return 0
  fi

  if [[ ! -d "${LOBSTER_ROOT}/.git" ]]; then
    echo "WARNING: ${LOBSTER_ROOT} is not a git repo — skipping pull"
    return 0
  fi

  echo "--- Pulling latest code ---"
  if [[ "$DRY_RUN" == true ]]; then
    echo "[dry-run] git -C ${LOBSTER_ROOT} pull --ff-only"
    return 0
  fi

  git -C "$LOBSTER_ROOT" pull --ff-only
}

refresh_deps() {
  echo "--- Refreshing dependencies ---"
  run bash "${LOBSTER_ROOT}/scripts/install.sh"
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

reload_serve_and_health_macos() {
  local agents="${HOME}/Library/LaunchAgents"
  local deploy="${LOBSTER_ROOT}/deploy/launchd"
  local serve_src="${deploy}/com.erik.lobster-price-monitor.serve.plist"
  local health_src="${deploy}/com.erik.lobster-price-monitor.health.plist"
  local serve_plist="${agents}/com.erik.lobster-price-monitor.serve.plist"
  local health_plist="${agents}/com.erik.lobster-price-monitor.health.plist"

  if [[ ! -f "$serve_src" ]]; then
    echo "ERROR: serve plist not found at $serve_src" >&2
    exit 1
  fi

  run mkdir -p "$agents"
  substitute_unit "$serve_src" "$serve_plist"
  if launchctl list 2>/dev/null | grep -q "com.erik.lobster-price-monitor.serve$"; then
    run launchctl unload "$serve_plist" || true
  fi
  run launchctl load "$serve_plist"

  if [[ "$SKIP_HEALTH" == true ]]; then
    echo "Skipping health agent reload (--skip-health)"
    return 0
  fi

  if [[ ! -f "$health_src" ]]; then
    echo "ERROR: health plist not found at $health_src" >&2
    exit 1
  fi
  substitute_unit "$health_src" "$health_plist"
  if launchctl list 2>/dev/null | grep -q "com.erik.lobster-price-monitor.health$"; then
    run launchctl unload "$health_plist" || true
  fi
  run launchctl load "$health_plist"
}

reload_ops_scrape_macos() {
  local agents="${HOME}/Library/LaunchAgents"
  local ops_src="${LOBSTER_ROOT}/deploy/launchd/com.erik.lobster-price-monitor.scrape.ops.plist"
  local ops_plist="${agents}/com.erik.lobster-price-monitor.scrape.ops.plist"

  if [[ ! -f "$ops_src" ]]; then
    echo "ERROR: ops plist not found at $ops_src" >&2
    exit 1
  fi

  run mkdir -p "$agents"
  substitute_unit "$ops_src" "$ops_plist"
  if launchctl list 2>/dev/null | grep -q "${OPS_SCRAPE_LABEL}$"; then
    run launchctl unload "$ops_plist" || true
  fi
  run launchctl load "$ops_plist"
  echo "macOS ops scrape reloaded: $ops_plist"
}

reload_ops_scrape_linux() {
  local deploy="${LOBSTER_ROOT}/deploy/systemd"
  local ops_service="${deploy}/lobster-price-monitor-scrape.ops.service"
  local ops_timer="${deploy}/lobster-price-monitor-scrape.ops.timer"

  for src in "$ops_service" "$ops_timer"; do
    if [[ ! -f "$src" ]]; then
      echo "ERROR: ops unit not found at $src" >&2
      exit 1
    fi
    install_linux_unit "$src"
  done

  run sudo systemctl daemon-reload
  run sudo systemctl enable --now "$OPS_SCRAPE_TIMER"
  echo "Linux ops scrape reloaded: $OPS_SCRAPE_TIMER"
}

reload_serve_and_health_linux() {
  local deploy="${LOBSTER_ROOT}/deploy/systemd"
  local units=(
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
  else
    echo "Skipping health timer reload (--skip-health)"
  fi

  run sudo systemctl daemon-reload
  run sudo systemctl enable --now lobster-price-monitor-serve.service
  if [[ "$SKIP_HEALTH" == false ]]; then
    run sudo systemctl enable --now lobster-price-monitor-health.timer
  fi
}

reload_ops_scheduler() {
  echo "--- Reloading ops schedulers ---"
  case "$(uname -s)" in
    Darwin)
      reload_ops_scrape_macos
      reload_serve_and_health_macos
      ;;
    Linux)
      reload_ops_scrape_linux
      reload_serve_and_health_linux
      ;;
    *)
      echo "ERROR: upgrade_host.sh supports macOS and Linux only (got $(uname -s))" >&2
      exit 1
      ;;
  esac
}

reload_dry_run_scheduler() {
  echo "--- Reloading dry-run schedulers ---"
  local flags=(--lobster-root "$LOBSTER_ROOT" --skip-verify)
  [[ "$DRY_RUN" == true ]] && flags+=(--dry-run)
  [[ "$SKIP_HEALTH" == true ]] && flags+=(--skip-health)
  bash "${LOBSTER_ROOT}/scripts/install_scheduler.sh" "${flags[@]}"
}

reload_schedulers() {
  detect_scheduler_mode
  case "$SCHEDULER_MODE" in
    ops)
      reload_ops_scheduler
      ;;
    dry-run)
      reload_dry_run_scheduler
      ;;
    none)
      echo "WARNING: no schedulers loaded — skipping scheduler reload"
      ;;
  esac
}

confirm_scrape() {
  if [[ "$SKIP_SCRAPE" == true ]]; then
    echo "Skipping confirmation scrape (--skip-scrape)"
    return 0
  fi

  echo "--- Confirmation scrape ---"
  case "$SCHEDULER_MODE" in
    ops)
      run env LOBSTER_ALERTS=1 "${LOBSTER_ROOT}/scripts/run_scrape.sh"
      ;;
    *)
      run "${LOBSTER_ROOT}/.venv/bin/python" "${LOBSTER_ROOT}/scripts/scrape_markets.py" --no-alerts
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
    if [[ "$SCHEDULER_MODE" == "ops" ]]; then
      echo "[dry-run] make -C ${LOBSTER_ROOT} verify-ops"
    elif [[ "$SCHEDULER_MODE" == "dry-run" ]]; then
      echo "[dry-run] make -C ${LOBSTER_ROOT} verify-deploy"
    else
      echo "[dry-run] make -C ${LOBSTER_ROOT} verify-production-ci"
    fi
    return 0
  fi

  case "$SCHEDULER_MODE" in
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
  echo "=== Gate D Wave 7 host upgrade ==="

  preflight
  pull_code
  refresh_deps
  reload_schedulers
  confirm_scrape
  run_verify

  echo "=== Host upgrade succeeded ==="
}

main
