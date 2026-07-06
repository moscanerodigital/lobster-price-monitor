#!/usr/bin/env bash
# Gate D Wave 9/12 host watchdog — status-driven Telegram on degraded/fatal.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOBSTER_ROOT="${LOBSTER_ROOT:-$ROOT}"
DRY_RUN=false
NOTIFY=false
FORCE=false
RECOVER=false
DEEP_RECOVER=false
RECOVERY_ATTEMPTED=false
DEEP_RECOVERY_ATTEMPTED=false
INITIAL_STATUS_CODE=0
CONSECUTIVE_FAILURES=0

usage() {
  cat <<'EOF'
Usage: scripts/watchdog_host.sh [--dry-run] [--notify] [--recover] [--deep-recover] [--force] [--lobster-root PATH]

Run status_host.sh checks and optionally send deduped Telegram alerts when
the host is degraded (exit 1) or fatal (exit 2).

With --recover, run recover_host.sh before re-checking status (also enabled
by LOBSTER_WATCHDOG_RECOVER=1 in the watchdog scheduler).

With --deep-recover, pass deep recovery to recover_host.sh (also enabled by
LOBSTER_WATCHDOG_DEEP_RECOVER=1 on ops watchdog units).

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
    --deep-recover)
      DEEP_RECOVER=true
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

if [[ "${LOBSTER_WATCHDOG_DEEP_RECOVER:-}" == "1" || "${LOBSTER_WATCHDOG_DEEP_RECOVER:-}" == "true" ]]; then
  DEEP_RECOVER=true
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

record_health_outcome() {
  local recovered=false
  if [[ "$STATUS_CODE" -eq 0 && "$RECOVERY_ATTEMPTED" == true && "$INITIAL_STATUS_CODE" -ne 0 ]]; then
    recovered=true
  fi

  local record_flags=(
    "${LOBSTER_ROOT}/scripts/host_health_state.py"
    --record
    --exit-code "$STATUS_CODE"
  )
  [[ "$RECOVERY_ATTEMPTED" == true ]] && record_flags+=(--recovery-attempted)
  [[ "$DEEP_RECOVERY_ATTEMPTED" == true ]] && record_flags+=(--deep-recovery-attempted)
  [[ "$recovered" == true ]] && record_flags+=(--recovered)

  if [[ "$DRY_RUN" == true ]]; then
    log "[dry-run] ${LOBSTER_ROOT}/.venv/bin/python ${record_flags[*]}"
    CONSECUTIVE_FAILURES=0
    return 0
  fi

  CONSECUTIVE_FAILURES="$("${LOBSTER_ROOT}/.venv/bin/python" "${record_flags[@]}")"
}

should_escalate_now() {
  if [[ "$DRY_RUN" == true ]]; then
    return 1
  fi
  "${LOBSTER_ROOT}/.venv/bin/python" -c "
import sys
sys.path.insert(0, '${LOBSTER_ROOT}/scripts')
from host_health_state import should_escalate
raise SystemExit(0 if should_escalate() else 1)
"
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

  local use_escalation=false
  if should_escalate_now; then
    use_escalation=true
    log "Watchdog: escalation threshold met (streak=${CONSECUTIVE_FAILURES})"
  fi

  local alert_flags=(--status-json "$STATUS_JSON" --exit-code "$status_code")
  [[ "$FORCE" == true ]] && alert_flags+=(--force)
  [[ "$DRY_RUN" == true ]] && alert_flags+=(--dry-run)
  [[ "$RECOVERY_ATTEMPTED" == true ]] && alert_flags+=(--recovery-attempted)
  [[ "$DEEP_RECOVERY_ATTEMPTED" == true ]] && alert_flags+=(--deep-recovery-attempted)

  if [[ "$use_escalation" == true ]]; then
    alert_flags+=(--escalation --consecutive-failures "$CONSECUTIVE_FAILURES")
    if [[ "$DRY_RUN" == true ]]; then
      log "[dry-run] would escalate for exit ${status_code} (streak=${CONSECUTIVE_FAILURES})"
    fi
  elif [[ "$DRY_RUN" == true ]]; then
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
  RECOVERY_ATTEMPTED=true
  local recover_flags=(--lobster-root "$LOBSTER_ROOT")
  [[ "$DRY_RUN" == true ]] && recover_flags+=(--dry-run)
  [[ "$FORCE" == true ]] && recover_flags+=(--force)
  [[ "$DEEP_RECOVER" == true ]] && recover_flags+=(--deep-recover)

  local recover_out
  set +e
  recover_out="$(bash "${LOBSTER_ROOT}/scripts/recover_host.sh" "${recover_flags[@]}" 2>&1)"
  set -e
  echo "$recover_out"
  if echo "$recover_out" | grep -q "deep upgrade"; then
    DEEP_RECOVERY_ATTEMPTED=true
  fi
}

main() {
  log "=== Gate D Wave 12 host watchdog ==="
  log "LOBSTER_ROOT=${LOBSTER_ROOT}"
  if [[ "$RECOVER" == true ]]; then
    log "Watchdog: auto-recovery enabled"
  fi
  if [[ "$DEEP_RECOVER" == true ]]; then
    log "Watchdog: deep recovery enabled"
  fi

  if [[ ! -x "${LOBSTER_ROOT}/.venv/bin/python" && "$DRY_RUN" != true ]]; then
    echo "ERROR: venv not found at ${LOBSTER_ROOT}/.venv — run scripts/bootstrap_host.sh first" >&2
    exit 2
  fi

  run_status
  INITIAL_STATUS_CODE="$STATUS_CODE"
  maybe_recover "$STATUS_CODE"
  if [[ "$RECOVER" == true && "$STATUS_CODE" -ne 0 ]]; then
    run_status
  fi
  record_health_outcome
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
