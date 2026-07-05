#!/usr/bin/env bash
# One-command no-alert scrape + board generation
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PY="${ROOT}/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "Run scripts/install.sh first" >&2
  exit 1
fi
"$PY" scripts/scrape_markets.py --no-alerts
"$PY" scripts/board.py --html
echo "Board: ${ROOT}/data/board.html"
