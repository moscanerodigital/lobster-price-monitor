"""Telegram send — dedupe-aware. Reads token from secrets file at runtime."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request

try:
    from . import state
    from .board_render import format_price, label_for, render_telegram_board
except ImportError:
    import state
    from board_render import format_price, label_for, render_telegram_board

from secrets import TELEGRAM_TOKEN_FILE as SECRETS
from secrets import get_telegram_chat_id

API = "https://api.telegram.org/bot{token}/{method}"

_alert_seen_cache: set[str] | None = None


def _get_chat_id() -> str:
    return get_telegram_chat_id()


def begin_alert_run() -> None:
    """Load alert dedupe keys once per scrape run."""
    global _alert_seen_cache
    _alert_seen_cache = state.seen_alert_keys()


def _alert_seen() -> set[str]:
    global _alert_seen_cache
    if _alert_seen_cache is None:
        _alert_seen_cache = state.seen_alert_keys()
    return _alert_seen_cache


def _mark_alert_sent(key: str) -> None:
    _alert_seen().add(key)


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
    status, body = _post("sendMessage", {"chat_id": _get_chat_id(), "text": text})
    return status == 200 and body.get("ok")


def alert_lobster_drop(
    market: str,
    tier: str,
    price: float,
    post_url: str,
    observed_at: str,
    threshold: float,
    *,
    confidence: int = 100,
) -> bool:
    key = f"lobster|{market}|{tier}|{price:.2f}"
    if key in _alert_seen():
        return False
    text = (
        f"🦞 *LOBSTER DROP* — {market}\n"
        f"```\n"
        f"  {label_for(tier):<16} ${price:.2f}/lb\n"
        f"  threshold ${threshold:.2f}  ·  conf {confidence}\n"
        f"```\n"
        f"seen: {observed_at}\n"
        f"{post_url}"
    )
    if send_telegram(text):
        state.append_jsonl(
            "alerts_sent.jsonl",
            {
                "key": key,
                "kind": "lobster_tier",
                "market": market,
                "tier": tier,
                "price": price,
                "confidence": confidence,
                "post_url": post_url,
                "observed_at": observed_at,
                "ts": observed_at,
            },
        )
        _mark_alert_sent(key)
        return True
    return False


def alert_oyster_drop(
    market: str,
    grade: str,
    price: float,
    post_url: str,
    observed_at: str,
    threshold: float,
    unit: str = "doz",
    *,
    confidence: int = 100,
) -> bool:
    key = f"oyster|{market}|{grade}|{price:.2f}|{unit}"
    if key in _alert_seen():
        return False
    text = (
        f"🦪 *OYSTER DROP* — {market}\n"
        f"```\n"
        f"  {label_for(grade):<16} ${price:.2f}/{unit}\n"
        f"  threshold ${threshold:.2f}/{unit}  ·  conf {confidence}\n"
        f"```\n"
        f"seen: {observed_at}\n"
        f"{post_url}"
    )
    if send_telegram(text):
        state.append_jsonl(
            "alerts_sent.jsonl",
            {
                "key": key,
                "kind": "oyster_tier",
                "market": market,
                "tier": grade,
                "price": price,
                "unit": unit,
                "confidence": confidence,
                "post_url": post_url,
                "observed_at": observed_at,
                "ts": observed_at,
            },
        )
        _mark_alert_sent(key)
        return True
    return False


def alert_specials_post(
    market: str,
    post_url: str,
    snippet: str,
    observed_at: str,
    *,
    special_items: list[dict],
    source: str = "facebook",
) -> bool:
    """AC4b-compliant specials alert with structured item list. Dedupes by (market|post_id)."""
    post_id = post_url.rstrip("/").split("/")[-1] if post_url else "unknown"
    key = f"special|{market}|{post_id}"
    if key in _alert_seen():
        return False

    board_block = render_telegram_board(
        market,
        [
            {
                "key": item["key"],
                "price": item["price"],
                "unit": item["unit"],
                "price_str": format_price(item["price"], item["unit"]),
            }
            for item in special_items[:8]
        ],
        heading="TODAY'S CATCH",
        emoji="📣",
    )
    text = f"{board_block}\nseen: {observed_at}\n{post_url}"

    if send_telegram(text):
        state.append_jsonl(
            "alerts_sent.jsonl",
            {
                "key": key,
                "kind": "special",
                "market": market,
                "post_id": post_id,
                "post_url": post_url,
                "source": source,
                "special_items": special_items,
                "observed_at": observed_at,
                "ts": observed_at,
            },
        )
        _mark_alert_sent(key)
        return True
    return False


def alert_web_specials(
    market: str,
    post_url: str,
    observed_at: str,
    new_items: list[dict],
) -> bool:
    """Alert when web catalog specials change (new items vs last snapshot)."""
    if not new_items:
        return False
    sig = "|".join(
        f"{i['key']}:{i['price']:.2f}:{i['unit']}"
        for i in sorted(new_items, key=lambda x: x["key"])
    )
    key = f"web_special|{market}|{sig}"
    if key in _alert_seen():
        return False
    board_block = render_telegram_board(
        market,
        [
            {
                "key": item["key"],
                "price": item["price"],
                "unit": item["unit"],
                "price_str": format_price(item["price"], item["unit"]),
            }
            for item in new_items[:8]
        ],
        heading="WEB SPECIALS",
        emoji="📣",
    )
    text = f"{board_block}\nseen: {observed_at}\n{post_url}"
    if send_telegram(text):
        state.append_jsonl(
            "alerts_sent.jsonl",
            {
                "key": key,
                "kind": "special",
                "market": market,
                "post_url": post_url,
                "source": "web",
                "special_items": new_items,
                "observed_at": observed_at,
                "ts": observed_at,
            },
        )
        _mark_alert_sent(key)
        return True
    return False
