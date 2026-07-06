#!/usr/bin/env bash
# Gate D Wave 6 host teardown — demote ops if needed, uninstall all schedulers.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOBSTER_ROOT="${LOBSTER_ROOT:-$ROOT}"
DRY_RUN=false
SKIP_DEMOTE=false
SKIP_HEALTH=false
PURGE_FILES=false

OPS_SCRAPE_LABEL="com.erik.lobster-price-monitor.scrape.ops"
OPS_SCRAPE_TIMER="lobster-price-monitor-scrape.ops.timer"

usage() {
  cat <<'EOF'
Usage: scripts/teardown_host.sh [--dry-run] [--skip-demote] [--skip-health] [--purge-files] [--lobster-root PATH]

Full host teardown:
  1. Preflight (warn if venv missing)
  2. Demote ops → dry-run if ops scheduler loaded (unless --skip-demote)
  3. Uninstall all schedulers (scrape, serve, health)
  4. Post-check: no schedulers loaded
  5. Optional health report (non-fatal if degraded)

Does not remove .venv, data/, or the repo clone.

Set LOBSTER_ROOT to override install path (default: repo root).
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    --skip-demote)
      SKIP_DEMOTE=true
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

preflight() {
  if [[ ! -x "${LOBSTER_ROOT}/.venv/bin/python" ]]; then
    echo "WARNING: venv not found at ${LOBSTER_ROOT}/.venv — continuing with scheduler removal"
  else
    echo "Preflight OK (LOBSTER_ROOT=$LOBSTER_ROOT)"
  fi
}

maybe_demote() {
  if [[ "$SKIP_DEMOTE" == true ]]; then
    echo "Skipping ops demotion (--skip-demote)"
    return 0
  fi

  if ops_loaded; then
    echo "--- Demoting ops scheduler to dry-run ---"
    bash "${LOBSTER_ROOT}/scripts/demote_ops.sh" \
      --lobster-root "$LOBSTER_ROOT" \
      $(dry_flag)
  else
    echo "Ops scheduler not loaded — skipping demote"
  fi
}

uninstall_schedulers() {
  echo "--- Uninstalling all schedulers ---"
  [[ "$PURGE_FILES" == true ]] && echo "Purge installed unit files after unload (--purge-files)"
  local flags=(--lobster-root "$LOBSTER_ROOT")
  [[ "$DRY_RUN" == true ]] && flags+=(--dry-run)
  [[ "$SKIP_HEALTH" == true ]] && flags+=(--skip-health)
  [[ "$PURGE_FILES" == true ]] && flags+=(--purge-files)
  bash "${LOBSTER_ROOT}/scripts/uninstall_scheduler.sh" "${flags[@]}"
}

optional_health() {
  local py="${LOBSTER_ROOT}/.venv/bin/python"
  if [[ ! -x "$py" ]]; then
    echo "Skipping health report (no venv)"
    return 0
  fi
  if [[ "$DRY_RUN" == true ]]; then
    echo "[dry-run] ${py} scripts/health_check.py"
    return 0
  fi
  echo "--- Health report (informational) ---"
  "$py" "${LOBSTER_ROOT}/scripts/health_check.py" || true
}

main() {
  echo "=== Gate D host teardown ==="

  preflight
  maybe_demote
  uninstall_schedulers
  optional_health

  echo "=== Host teardown succeeded ==="
  echo "Schedulers removed. Board data may remain under ${LOBSTER_ROOT}/data/"
  echo "Re-deploy with: make deploy-host"
}

main
