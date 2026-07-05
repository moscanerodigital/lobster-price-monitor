"""Telegram send — dedupe-aware. Reads token from secrets file at runtime."""
from __future__ import annotations
import json
import os
import urllib.request
import urllib.parse
from pathlib import Path

# Support both package-relative and direct import
try:
    from . import state
except ImportError:
    import state

SECRETS = Path(os.path.expanduser("~/.openclaw/secrets/telegram/herb.token"))
ERIK_CHAT_ID = "6700324874"
API = "https://api.telegram.org/bot{token}/{method}"


def _get_token() -> str:
    if not SECRETS.exists():
        raise RuntimeError(f"Missing token file: {SECRETS}")
    return SECRETS.read_text(encoding="utf-8").strip()


def _post(method: str, payload: dict) -> tuple[int, dict]:
    token = _get_token()
    url = API.format(token=token, method=method)
    data = urllib.parse.urlencode(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return 0, {"error": str(e)}


def send_telegram(text: str) -> bool:
    """Send a plain-text message to Erik's home channel. Returns True on success."""
    status, body = _post("sendMessage", {"chat_id": ERIK_CHAT_ID, "text": text})
    ok = status == 200 and body.get("ok")
    return ok


def alert_lobster_drop(market: str, tier: str, price: float, post_url: str, observed_at: str, threshold: float) -> bool:
    """Send a lobster-tier-drop alert. Dedupes by (market|tier|price). Returns True if sent (not deduped)."""
    key = f"lobster|{market}|{tier}|{price:.2f}"
    seen = state.seen_alert_keys()
    if key in seen:
        return False
    text = (
        f"🦞 *Lobster price drop* — {market}\n"
        f"   {tier}: ${price:.2f}/lb (threshold ${threshold:.2f})\n"
        f"   seen: {observed_at}\n"
        f"   {post_url}"
    )
    if send_telegram(text):
        state.append_jsonl("alerts_sent.jsonl", {
            "key": key, "kind": "lobster_tier", "market": market,
            "tier": tier, "price": price, "post_url": post_url,
            "observed_at": observed_at, "ts": observed_at,
        })
        return True
    return False


def alert_oyster_drop(market: str, grade: str, price: float, post_url: str, observed_at: str, threshold: float, unit: str = "doz") -> bool:
    """Send an oyster-tier-drop alert. Dedupes by (market|grade|price|unit).
    Returns True if sent (not deduped)."""
    key = f"oyster|{market}|{grade}|{price:.2f}|{unit}"
    seen = state.seen_alert_keys()
    if key in seen:
        return False
    text = (
        f"🦪 *Oyster price drop* — {market}\n"
        f"   {grade}: ${price:.2f}/{unit} (threshold ${threshold:.2f}/{unit})\n"
        f"   seen: {observed_at}\n"
        f"   {post_url}"
    )
    if send_telegram(text):
        state.append_jsonl("alerts_sent.jsonl", {
            "key": key, "kind": "oyster_tier", "market": market,
            "tier": grade, "price": price, "unit": unit,
            "post_url": post_url, "observed_at": observed_at, "ts": observed_at,
        })
        return True
    return False


def alert_special(market: str, post_url: str, snippet: str, observed_at: str) -> bool:
    """Send a new-specials-post alert. Dedupes by (market|post_id)."""
    # post_url contains the post_id; extract it
    # FB post URLs look like: https://www.facebook.com/<handle>/posts/<postid>
    post_id = post_url.rstrip("/").split("/")[-1] if post_url else "unknown"
    key = f"special|{market}|{post_id}"
    seen = state.seen_alert_keys()
    if key in seen:
        return False
    snippet = (snippet or "")[:280]
    text = (
        f"📣 *New specials post* — {market}\n"
        f"   {snippet}\n"
        f"   {post_url}"
    )
    if send_telegram(text):
        state.append_jsonl("alerts_sent.jsonl", {
            "key": key, "kind": "special", "market": market,
            "post_id": post_id, "post_url": post_url,
            "observed_at": observed_at, "ts": observed_at,
        })
        return True
    return False
