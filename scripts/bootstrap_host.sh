#!/usr/bin/env bash
# Phase 1 host bootstrap — install, dry-run scrape, verify gates, health, serve smoke.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOBSTER_ROOT="${LOBSTER_ROOT:-$ROOT}"
DRY_RUN=false
SKIP_SERVE_SMOKE=false
SKIP_VERIFY=false
SERVE_PORT="${LOBSTER_SERVE_PORT:-8765}"

usage() {
  cat <<'EOF'
Usage: scripts/bootstrap_host.sh [--dry-run] [--skip-serve-smoke] [--skip-verify] [--lobster-root PATH]

Phase 1 host bootstrap (NEXT_AGENT):
  1. Preflight secrets (no Telegram required) and LOBSTER_ROOT
  2. scripts/install.sh
  3. scripts/dry_run.sh
  4. make verify, verify-production-ci, verify-ops-ci
  5. health_check.py
  6. Optional serve smoke test (curl board.html)

Set LOBSTER_ROOT to override install path (default: repo root).
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    --skip-serve-smoke)
      SKIP_SERVE_SMOKE=true
      shift
      ;;
    --skip-verify)
      SKIP_VERIFY=true
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

preflight() {
  if [[ ! -w "$LOBSTER_ROOT" ]]; then
    echo "ERROR: LOBSTER_ROOT is not writable: $LOBSTER_ROOT" >&2
    exit 1
  fi
  mkdir -p "${LOBSTER_ROOT}/logs" "${LOBSTER_ROOT}/data"
  bash "${LOBSTER_ROOT}/scripts/preflight_secrets.sh" $([[ "$DRY_RUN" == true ]] && echo --dry-run)
  echo "Preflight OK (LOBSTER_ROOT=$LOBSTER_ROOT)"
}

serve_smoke() {
  if [[ "$SKIP_SERVE_SMOKE" == true ]]; then
    echo "Skipping serve smoke test"
    return 0
  fi
  if [[ "$DRY_RUN" == true ]]; then
    echo "[dry-run] ${LOBSTER_ROOT}/.venv/bin/python scripts/serve_board.py --port ${SERVE_PORT} --host 127.0.0.1 &"
    echo "[dry-run] curl -sf http://127.0.0.1:${SERVE_PORT}/board.html | head -c 200"
    echo "[dry-run] kill serve smoke server"
    return 0
  fi

  local py="${LOBSTER_ROOT}/.venv/bin/python"
  if [[ ! -x "$py" ]]; then
    echo "ERROR: venv not found — run install first" >&2
    exit 1
  fi

  "$py" "${LOBSTER_ROOT}/scripts/serve_board.py" --port "$SERVE_PORT" --host 127.0.0.1 &
  local serve_pid=$!
  local ok=false
  trap 'kill "$serve_pid" 2>/dev/null || true' EXIT

  for _ in $(seq 1 20); do
    if curl -sf "http://127.0.0.1:${SERVE_PORT}/board.html" | head -c 200 >/dev/null 2>&1; then
      ok=true
      break
    fi
    sleep 0.25
  done

  kill "$serve_pid" 2>/dev/null || true
  wait "$serve_pid" 2>/dev/null || true
  trap - EXIT

  if [[ "$ok" != true ]]; then
    echo "ERROR: serve smoke test failed — board.html not reachable on port ${SERVE_PORT}" >&2
    exit 1
  fi
  echo "  ✓ serve smoke test passed (port ${SERVE_PORT})"
}

run_verify() {
  if [[ "$SKIP_VERIFY" == true ]]; then
    echo "Skipping verify suite"
    return 0
  fi
  run make -C "$LOBSTER_ROOT" verify
  run make -C "$LOBSTER_ROOT" verify-production-ci
  run make -C "$LOBSTER_ROOT" verify-ops-ci
}

main() {
  echo "=== Gate D Phase 1 host bootstrap ==="
  preflight
  run bash "${LOBSTER_ROOT}/scripts/install.sh"
  run bash "${LOBSTER_ROOT}/scripts/dry_run.sh"
  run_verify
  run "${LOBSTER_ROOT}/.venv/bin/python" "${LOBSTER_ROOT}/scripts/health_check.py"
  serve_smoke
  echo "=== Phase 1 bootstrap succeeded ==="
}

main
