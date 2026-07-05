"""Telegram send — dedupe-aware. Reads token from secrets file at runtime."""
from __future__ import annotations
import json
import os
import urllib.request
import urllib.parse
from pathlib import Path

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
    status, body = _post("sendMessage", {"chat_id": ERIK_CHAT_ID, "text": text})
    return status == 200 and body.get("ok")


def alert_lobster_drop(
    market: str, tier: str, price: float, post_url: str,
    observed_at: str, threshold: float, *, confidence: int = 100,
) -> bool:
    key = f"lobster|{market}|{tier}|{price:.2f}"
    seen = state.seen_alert_keys()
    if key in seen:
        return False
    text = (
        f"🦞 *Lobster price drop* — {market}\n"
        f"   {tier}: ${price:.2f}/lb (threshold ${threshold:.2f}, conf {confidence})\n"
        f"   seen: {observed_at}\n"
        f"   {post_url}"
    )
    if send_telegram(text):
        state.append_jsonl("alerts_sent.jsonl", {
            "key": key, "kind": "lobster_tier", "market": market,
            "tier": tier, "price": price, "confidence": confidence,
            "post_url": post_url, "observed_at": observed_at, "ts": observed_at,
        })
        return True
    return False


def alert_oyster_drop(
    market: str, grade: str, price: float, post_url: str,
    observed_at: str, threshold: float, unit: str = "doz", *, confidence: int = 100,
) -> bool:
    key = f"oyster|{market}|{grade}|{price:.2f}|{unit}"
    seen = state.seen_alert_keys()
    if key in seen:
        return False
    text = (
        f"🦪 *Oyster price drop* — {market}\n"
        f"   {grade}: ${price:.2f}/{unit} (threshold ${threshold:.2f}/{unit}, conf {confidence})\n"
        f"   seen: {observed_at}\n"
        f"   {post_url}"
    )
    if send_telegram(text):
        state.append_jsonl("alerts_sent.jsonl", {
            "key": key, "kind": "oyster_tier", "market": market,
            "tier": grade, "price": price, "unit": unit, "confidence": confidence,
            "post_url": post_url, "observed_at": observed_at, "ts": observed_at,
        })
        return True
    return False


def alert_special(
    market: str, post_url: str, snippet: str, observed_at: str,
    *, special_items: list[dict] | None = None,
) -> bool:
    """Legacy wrapper — delegates to alert_specials_post."""
    return alert_specials_post(
        market, post_url, snippet, observed_at, special_items=special_items or [],
    )


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
    seen = state.seen_alert_keys()
    if key in seen:
        return False

    lines = [f"📣 *New specials* — {market}"]
    for item in special_items[:8]:
        conf = item.get("confidence", "?")
        lines.append(
            f"   • {item['key']}: ${item['price']:.2f}/{item['unit']} (conf {conf})"
        )
    if not special_items:
        lines.append(f"   {(snippet or '')[:200]}")
    lines.append(f"   seen: {observed_at}")
    lines.append(f"   {post_url}")
    text = "\n".join(lines)

    if send_telegram(text):
        state.append_jsonl("alerts_sent.jsonl", {
            "key": key, "kind": "special", "market": market,
            "post_id": post_id, "post_url": post_url, "source": source,
            "special_items": special_items,
            "observed_at": observed_at, "ts": observed_at,
        })
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
    sig = "|".join(f"{i['key']}:{i['price']:.2f}:{i['unit']}" for i in sorted(new_items, key=lambda x: x["key"]))
    key = f"web_special|{market}|{sig}"
    seen = state.seen_alert_keys()
    if key in seen:
        return False
    lines = [f"📣 *Web specials update* — {market}"]
    for item in new_items[:8]:
        conf = item.get("confidence", "?")
        lines.append(
            f"   • {item['key']}: ${item['price']:.2f}/{item['unit']} (conf {conf})"
        )
    lines.append(f"   seen: {observed_at}")
    lines.append(f"   {post_url}")
    text = "\n".join(lines)
    if send_telegram(text):
        state.append_jsonl("alerts_sent.jsonl", {
            "key": key, "kind": "special", "market": market,
            "post_url": post_url, "source": "web",
            "special_items": new_items, "observed_at": observed_at, "ts": observed_at,
        })
        return True
    return False
