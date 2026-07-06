#!/usr/bin/env bash
# Unified host deploy orchestrator — Phase 1 bootstrap, Phase 2 scheduler, optional Phase 3 ops.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOBSTER_ROOT="${LOBSTER_ROOT:-$ROOT}"
DRY_RUN=false
PHASE="all"
SKIP_HEALTH=false
PROMOTE=false
TEARDOWN=false
UPGRADE=false
STATUS=false
WATCHDOG=false
RECOVER=false
PURGE_FILES=false

usage() {
  cat <<'EOF'
Usage: scripts/deploy_host.sh [--dry-run] [--phase 1|2|3|all] [--skip-health] [--promote] [--teardown] [--upgrade] [--status] [--watchdog] [--recover] [--purge-files] [--lobster-root PATH]

Unified host deployment orchestrator:
  Phase 1: bootstrap_host.sh (install + dry-run + verify + health)
  Phase 2: install_scheduler.sh (dry-run scrape + serve schedulers)
  Phase 3: promote_ops.sh (live Telegram — requires --promote or --phase 3)

Phase 3 never runs on --phase all unless --promote is set.

With --teardown, run teardown_host.sh instead (remove all schedulers).
With --upgrade, run upgrade_host.sh instead (in-place code/deps refresh).
With --status, run status_host.sh instead (read-only host diagnostics).
With --watchdog, run watchdog_host.sh instead (status + optional Telegram alert).
With --recover, run recover_host.sh instead (status-driven auto-recovery).
--teardown, --upgrade, --status, --watchdog, and --recover are mutually exclusive with phase flags.

Set LOBSTER_ROOT to override install path (default: repo root).
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    --phase)
      PHASE="$2"
      shift 2
      ;;
    --skip-health)
      SKIP_HEALTH=true
      shift
      ;;
    --promote)
      PROMOTE=true
      shift
      ;;
    --teardown)
      TEARDOWN=true
      shift
      ;;
    --upgrade)
      UPGRADE=true
      shift
      ;;
    --status)
      STATUS=true
      shift
      ;;
    --watchdog)
      WATCHDOG=true
      shift
      ;;
    --recover)
      RECOVER=true
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

case "$PHASE" in
  1|2|3|all) ;;
  *)
    echo "ERROR: invalid --phase '$PHASE' (use 1, 2, 3, or all)" >&2
    exit 1
    ;;
esac

dry_flag() {
  [[ "$DRY_RUN" == true ]] && echo --dry-run
}

phase1() {
  echo "--- Phase 1: bootstrap ---"
  bash "${LOBSTER_ROOT}/scripts/bootstrap_host.sh" \
    --lobster-root "$LOBSTER_ROOT" \
    $(dry_flag)
}

phase2() {
  echo "--- Phase 2: scheduler install ---"
  local health_flag=()
  [[ "$SKIP_HEALTH" == true ]] && health_flag=(--skip-health)
  bash "${LOBSTER_ROOT}/scripts/install_scheduler.sh" \
    --lobster-root "$LOBSTER_ROOT" \
    $(dry_flag) \
    "${health_flag[@]}"
}

phase3() {
  echo "--- Phase 3: ops promotion (live Telegram) ---"
  bash "${LOBSTER_ROOT}/scripts/promote_ops.sh" $(dry_flag)
}

teardown() {
  echo "--- Host teardown ---"
  local flags=(--lobster-root "$LOBSTER_ROOT")
  [[ "$DRY_RUN" == true ]] && flags+=(--dry-run)
  [[ "$SKIP_HEALTH" == true ]] && flags+=(--skip-health)
  [[ "$PURGE_FILES" == true ]] && flags+=(--purge-files)
  bash "${LOBSTER_ROOT}/scripts/teardown_host.sh" "${flags[@]}"
}

upgrade() {
  echo "--- Host upgrade ---"
  local flags=(--lobster-root "$LOBSTER_ROOT")
  [[ "$DRY_RUN" == true ]] && flags+=(--dry-run)
  [[ "$SKIP_HEALTH" == true ]] && flags+=(--skip-health)
  bash "${LOBSTER_ROOT}/scripts/upgrade_host.sh" "${flags[@]}"
}

status() {
  echo "--- Host status ---"
  local flags=(--lobster-root "$LOBSTER_ROOT")
  [[ "$DRY_RUN" == true ]] && flags+=(--dry-run)
  bash "${LOBSTER_ROOT}/scripts/status_host.sh" "${flags[@]}"
}

watchdog() {
  echo "--- Host watchdog ---"
  local flags=(--lobster-root "$LOBSTER_ROOT")
  [[ "$DRY_RUN" == true ]] && flags+=(--dry-run)
  bash "${LOBSTER_ROOT}/scripts/watchdog_host.sh" "${flags[@]}"
}

recover() {
  echo "--- Host recovery ---"
  local flags=(--lobster-root "$LOBSTER_ROOT")
  [[ "$DRY_RUN" == true ]] && flags+=(--dry-run)
  bash "${LOBSTER_ROOT}/scripts/recover_host.sh" "${flags[@]}"
}

main() {
  local exclusive_count=0
  [[ "$TEARDOWN" == true ]] && exclusive_count=$((exclusive_count + 1))
  [[ "$UPGRADE" == true ]] && exclusive_count=$((exclusive_count + 1))
  [[ "$STATUS" == true ]] && exclusive_count=$((exclusive_count + 1))
  [[ "$WATCHDOG" == true ]] && exclusive_count=$((exclusive_count + 1))
  [[ "$RECOVER" == true ]] && exclusive_count=$((exclusive_count + 1))
  if [[ $exclusive_count -gt 1 ]]; then
    echo "ERROR: --teardown, --upgrade, --status, --watchdog, and --recover are mutually exclusive" >&2
    exit 1
  fi

  if [[ "$TEARDOWN" == true ]]; then
    echo "=== Gate D host teardown ==="
    teardown
    echo "=== deploy_host.sh finished ==="
    return 0
  fi

  if [[ "$UPGRADE" == true ]]; then
    echo "=== Gate D host upgrade ==="
    upgrade
    echo "=== deploy_host.sh finished ==="
    return 0
  fi

  if [[ "$STATUS" == true ]]; then
    echo "=== Gate D host status ==="
    status
    echo "=== deploy_host.sh finished ==="
    return 0
  fi

  if [[ "$WATCHDOG" == true ]]; then
    echo "=== Gate D host watchdog ==="
    watchdog
    echo "=== deploy_host.sh finished ==="
    return 0
  fi

  if [[ "$RECOVER" == true ]]; then
    echo "=== Gate D host recovery ==="
    recover
    echo "=== deploy_host.sh finished ==="
    return 0
  fi

  echo "=== Gate D host deploy (phase=${PHASE}) ==="

  case "$PHASE" in
    1)
      phase1
      echo "Next: make install-scheduler  (or deploy_host.sh --phase 2)"
      ;;
    2)
      phase2
      echo "Next: make promote-ops  (or deploy_host.sh --phase 3 --promote)"
      ;;
    3)
      phase3
      echo "Host deploy complete — ops scheduler with live alerts"
      ;;
    all)
      phase1
      phase2
      if [[ "$PROMOTE" == true ]]; then
        phase3
        echo "Host deploy complete — all phases including ops promotion"
      else
        echo "Phases 1–2 complete. Run with --promote to enable live Telegram alerts:"
        echo "  bash scripts/deploy_host.sh --phase 3 --promote"
        echo "  # or: make promote-ops"
      fi
      ;;
  esac

  echo "=== deploy_host.sh finished ==="
}

main
