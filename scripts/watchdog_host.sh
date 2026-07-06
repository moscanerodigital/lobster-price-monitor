#!/usr/bin/env bash
# Gate D Wave 9 host watchdog — status-driven Telegram on degraded/fatal.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOBSTER_ROOT="${LOBSTER_ROOT:-$ROOT}"
DRY_RUN=false
NOTIFY=false
FORCE=false
RECOVER=false

usage() {
  cat <<'EOF'
Usage: scripts/watchdog_host.sh [--dry-run] [--notify] [--recover] [--force] [--lobster-root PATH]

Run status_host.sh checks and optionally send deduped Telegram alerts when
the host is degraded (exit 1) or fatal (exit 2).

With --recover, run recover_host.sh before re-checking status (also enabled
by LOBSTER_WATCHDOG_RECOVER=1 in the watchdog scheduler).

Default: check-only (no Telegram). Use --notify or set LOBSTER_WATCHDOG_ALERTS=1
to send alerts (requires Telegram secrets).

Exit codes mirror status_host.sh: 0 healthy, 1 degraded, 2 fatal preflight.

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
    --recover)
      RECOVER=true
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

if [[ "${LOBSTER_WATCHDOG_ALERTS:-}" == "1" || "${LOBSTER_WATCHDOG_ALERTS:-}" == "true" ]]; then
  NOTIFY=true
fi

if [[ "${LOBSTER_WATCHDOG_RECOVER:-}" == "1" || "${LOBSTER_WATCHDOG_RECOVER:-}" == "true" ]]; then
  RECOVER=true
fi

log() {
  echo "$@"
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

maybe_notify() {
  local status_code="$1"

  if [[ "$status_code" -eq 0 ]]; then
    log "Watchdog: host healthy — no alert"
    return 0
  fi

  if [[ "$NOTIFY" != true ]]; then
    log "Watchdog: host unhealthy (exit ${status_code}) — check-only, no --notify"
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

  local alert_flags=(--status-json "$STATUS_JSON" --exit-code "$status_code")
  [[ "$FORCE" == true ]] && alert_flags+=(--force)
  [[ "$DRY_RUN" == true ]] && alert_flags+=(--dry-run)

  if [[ "$DRY_RUN" == true ]]; then
    log "[dry-run] would alert for exit ${status_code}"
  fi

  "${LOBSTER_ROOT}/.venv/bin/python" "${LOBSTER_ROOT}/scripts/watchdog_alert.py" "${alert_flags[@]}"
}

maybe_recover() {
  local status_code="$1"

  if [[ "$RECOVER" != true ]]; then
    return 0
  fi
  if [[ "$status_code" -eq 0 ]]; then
    return 0
  fi
  if [[ "$status_code" -ge 2 ]]; then
    log "Watchdog: fatal preflight — skipping recovery"
    return 0
  fi

  log "--- Watchdog: attempting host recovery ---"
  local recover_flags=(--lobster-root "$LOBSTER_ROOT")
  [[ "$DRY_RUN" == true ]] && recover_flags+=(--dry-run)
  [[ "$FORCE" == true ]] && recover_flags+=(--force)
  bash "${LOBSTER_ROOT}/scripts/recover_host.sh" "${recover_flags[@]}" || true
}

main() {
  log "=== Gate D Wave 9 host watchdog ==="
  log "LOBSTER_ROOT=${LOBSTER_ROOT}"
  if [[ "$RECOVER" == true ]]; then
    log "Watchdog: auto-recovery enabled"
  fi

  if [[ ! -x "${LOBSTER_ROOT}/.venv/bin/python" && "$DRY_RUN" != true ]]; then
    echo "ERROR: venv not found at ${LOBSTER_ROOT}/.venv — run scripts/bootstrap_host.sh first" >&2
    exit 2
  fi

  run_status
  maybe_recover "$STATUS_CODE"
  if [[ "$RECOVER" == true && "$STATUS_CODE" -ne 0 ]]; then
    run_status
  fi
  maybe_notify "$STATUS_CODE" || true

  if [[ "$DRY_RUN" == true ]]; then
    log "=== Watchdog dry-run complete (exit 0) ==="
    exit 0
  fi

  if [[ "$STATUS_CODE" -eq 0 ]]; then
    log "=== Watchdog: HEALTHY ==="
  elif [[ "$STATUS_CODE" -eq 1 ]]; then
    log "=== Watchdog: DEGRADED ==="
  else
    log "=== Watchdog: FATAL ==="
  fi

  exit "$STATUS_CODE"
}

main
