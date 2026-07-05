#!/usr/bin/env bash
# One-command dependency install into project venv
# requirements.txt mirrors pyproject.toml dependencies
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
echo "Ready: $ROOT/.venv/bin/python"
