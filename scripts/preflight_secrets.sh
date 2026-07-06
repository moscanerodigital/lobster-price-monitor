#!/usr/bin/env bash
# Shared secrets preflight for host bootstrap and ops promotion.
set -euo pipefail

REQUIRE_TELEGRAM=false
DRY_RUN=false

usage() {
  cat <<'EOF'
Usage: scripts/preflight_secrets.sh [--require-telegram] [--dry-run]

Check ~/.openclaw/secrets paths without printing secret values.
Exit 0 with summary; exit 1 with actionable errors.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --require-telegram)
      REQUIRE_TELEGRAM=true
      shift
      ;;
    --dry-run)
      DRY_RUN=true
      shift
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

SECRETS_ROOT="${HOME}/.openclaw/secrets"
TOKEN_FILE="${SECRETS_ROOT}/telegram/herb.token"
CHAT_ID_FILE="${SECRETS_ROOT}/telegram/chat_id"
FB_COOKIES_FILE="${SECRETS_ROOT}/facebook-cookies.json"
GOOGLE_KEY_FILE="${SECRETS_ROOT}/google-cse.key"
GOOGLE_CX_FILE="${SECRETS_ROOT}/google-cse.cx"

FAILED=false
WARNINGS=0

check_file_nonempty() {
  local label="$1"
  local path="$2"
  local required="$3"

  if [[ "$DRY_RUN" == true ]]; then
    echo "[dry-run] check ${label}: ${path}"
    return 0
  fi

  if [[ ! -f "$path" ]]; then
    if [[ "$required" == true ]]; then
      echo "ERROR: missing required secret file: ${path}" >&2
      FAILED=true
    else
      echo "WARNING: optional secret missing: ${path}" >&2
      WARNINGS=$((WARNINGS + 1))
    fi
    return 0
  fi

  if [[ ! -s "$path" ]]; then
    if [[ "$required" == true ]]; then
      echo "ERROR: required secret file is empty: ${path}" >&2
      FAILED=true
    else
      echo "WARNING: optional secret file is empty: ${path}" >&2
      WARNINGS=$((WARNINGS + 1))
    fi
    return 0
  fi

  echo "  ✓ ${label} present"
}

check_chat_id() {
  if [[ -n "${LOBSTER_TELEGRAM_CHAT_ID:-}" ]]; then
    echo "  ✓ Telegram chat ID from LOBSTER_TELEGRAM_CHAT_ID"
    return 0
  fi
  check_file_nonempty "Telegram chat ID" "$CHAT_ID_FILE" false
}

echo "=== Secrets preflight ==="

if [[ "$REQUIRE_TELEGRAM" == true ]]; then
  check_file_nonempty "Telegram bot token" "$TOKEN_FILE" true
  check_chat_id
else
  if [[ "$DRY_RUN" == true ]]; then
    echo "[dry-run] skip required Telegram token check"
  elif [[ -f "$TOKEN_FILE" && -s "$TOKEN_FILE" ]]; then
    echo "  ✓ Telegram bot token present (optional for this phase)"
  else
    echo "  · Telegram bot token not configured (OK for dry-run phases)"
  fi
  check_chat_id
fi

check_file_nonempty "Facebook cookies" "$FB_COOKIES_FILE" false

if [[ "$DRY_RUN" == true ]]; then
  echo "[dry-run] check Google CSE key: ${GOOGLE_KEY_FILE}"
  echo "[dry-run] check Google CSE cx: ${GOOGLE_CX_FILE}"
else
  if [[ -f "$GOOGLE_KEY_FILE" && -s "$GOOGLE_KEY_FILE" && -f "$GOOGLE_CX_FILE" && -s "$GOOGLE_CX_FILE" ]]; then
    echo "  ✓ Google CSE credentials present"
  else
    echo "WARNING: Google CSE not fully configured (${GOOGLE_KEY_FILE}, ${GOOGLE_CX_FILE})" >&2
    WARNINGS=$((WARNINGS + 1))
  fi
fi

if [[ "$FAILED" == true ]]; then
  echo "Secrets preflight FAILED" >&2
  exit 1
fi

echo "Secrets preflight OK (${WARNINGS} optional warning(s))"
exit 0
