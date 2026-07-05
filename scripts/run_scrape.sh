#!/usr/bin/env bash
# Run a no-alert scrape and regenerate data/board.html (scrape_markets.py writes the board).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${ROOT}/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  PY=python3
fi

mkdir -p "${ROOT}/logs"
exec "$PY" "${ROOT}/scripts/scrape_markets.py" --no-alerts "$@"
