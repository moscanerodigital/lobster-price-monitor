#!/usr/bin/env bash
# Unified host deploy orchestrator — Phase 1 bootstrap, Phase 2 scheduler, optional Phase 3 ops.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOBSTER_ROOT="${LOBSTER_ROOT:-$ROOT}"
DRY_RUN=false
PHASE="all"
SKIP_HEALTH=false
PROMOTE=false

usage() {
  cat <<'EOF'
Usage: scripts/deploy_host.sh [--dry-run] [--phase 1|2|3|all] [--skip-health] [--promote] [--lobster-root PATH]

Unified host deployment orchestrator:
  Phase 1: bootstrap_host.sh (install + dry-run + verify + health)
  Phase 2: install_scheduler.sh (dry-run scrape + serve schedulers)
  Phase 3: promote_ops.sh (live Telegram — requires --promote or --phase 3)

Phase 3 never runs on --phase all unless --promote is set.

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

main() {
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
