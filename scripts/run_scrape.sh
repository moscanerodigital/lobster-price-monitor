#!/usr/bin/env bash
# Run scrape and regenerate data/board.html (scrape_markets.py writes the board).
# Default: --no-alerts. Set LOBSTER_ALERTS=1 or LOBSTER_ALERTS=true for live Telegram.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${ROOT}/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  PY=python3
fi

ALERT_FLAG="--no-alerts"
if [[ "${LOBSTER_ALERTS:-}" == "1" || "${LOBSTER_ALERTS:-}" == "true" ]]; then
  ALERT_FLAG="--alerts"
fi

mkdir -p "${ROOT}/logs"
exec "$PY" "${ROOT}/scripts/scrape_markets.py" "$ALERT_FLAG" "$@"
