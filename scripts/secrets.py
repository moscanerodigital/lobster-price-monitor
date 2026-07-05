"""Shared secrets and credential loading."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

FB_COOKIES_FILE = Path(os.path.expanduser("~/.openclaw/secrets/facebook-cookies.json"))
TELEGRAM_TOKEN_FILE = Path(os.path.expanduser("~/.openclaw/secrets/telegram/herb.token"))
TELEGRAM_CHAT_ID_FILE = Path(os.path.expanduser("~/.openclaw/secrets/telegram/chat_id"))
DEFAULT_TELEGRAM_CHAT_ID = "6700324874"


def load_fb_cookies() -> dict[str, str] | None:
    """Load Facebook session cookies from secrets file or Chrome."""
    if FB_COOKIES_FILE.exists():
        try:
            raw = FB_COOKIES_FILE.read_text(encoding="utf-8").strip()
            if raw:
                data = json.loads(raw)
                if isinstance(data, list):
                    jar = {
                        c["name"]: c["value"]
                        for c in data
                        if isinstance(c, dict) and c.get("name") and "value" in c
                    }
                    if jar:
                        return jar
                if isinstance(data, dict):
                    if "cookies" in data and isinstance(data["cookies"], dict):
                        return data["cookies"]
                    if any(k in data for k in ("c_user", "xs")):
                        return {k: str(v) for k, v in data.items()}
        except json.JSONDecodeError:
            logger.debug("Invalid JSON in Facebook cookies file", exc_info=True)
    try:
        import browser_cookie3

        chrome_cookies = browser_cookie3.chrome(domain_name=".facebook.com")
        jar = {c.name: c.value for c in chrome_cookies}
        if "c_user" in jar and "xs" in jar:
            return jar
    except Exception:
        logger.debug("Could not load Facebook cookies from Chrome", exc_info=True)
    return None


def get_telegram_chat_id() -> str:
    """Read Telegram chat ID from secrets file or environment."""
    env_id = os.environ.get("LOBSTER_TELEGRAM_CHAT_ID", "").strip()
    if env_id:
        return env_id
    if TELEGRAM_CHAT_ID_FILE.exists():
        chat_id = TELEGRAM_CHAT_ID_FILE.read_text(encoding="utf-8").strip()
        if chat_id:
            return chat_id
    return DEFAULT_TELEGRAM_CHAT_ID
