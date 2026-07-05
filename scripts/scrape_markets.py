#!/usr/bin/env python3
"""Main entrypoint: scrape markets, parse prices, gate, alert.

Run: python3 scripts/scrape_markets.py
"""
from __future__ import annotations
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from state import append_jsonl, last_web_specials, save_web_snapshot, seen_post_ids
from parse_prices import is_specials_post, parse_post, parse_post_with_meta
from quality_gate import gate_rows, source_quality_score
from send_alert import alert_lobster_drop, alert_oyster_drop, alert_specials_post, alert_web_specials

FB_COOKIES_FILE = Path(os.path.expanduser("~/.openclaw/secrets/facebook-cookies.json"))

LOBSTER_TIER_THRESHOLDS = {
    "chicks": 7.50,
    "soft_shell": 8.00,
    "old_shell": 8.50,
    "hard_shell": 9.50,
    "select": 10.00,
    "1.125lb": 7.50,
    "1.25lb": 8.00,
    "1.5lb": 9.00,
    "1.75lb": 10.00,
    "2lb_plus": 11.00,
}

OYSTER_TIER_THRESHOLDS = {
    "xl": 28.00,
    "jumbo": 26.00,
    "select": 22.00,
    "standard": 18.00,
    "single_select": 32.00,
    "named_variety": 24.00,
    "small": 18.00,
    "medium": 20.00,
    "large": 24.00,
    "pint": 30.00,
    "oyster": 22.00,
}

MARKETS: list[dict] = [
    {"name": "Ancient Mariner Lobster Co.", "location": "Westbrook", "fb_handle": "amlobsterco", "web": None},
    {"name": "Two Tides Seafood", "location": "Scarborough", "fb_handle": "100054888565201", "web": None},
    {"name": "Scarborough Fish & Lobster", "location": "Scarborough", "fb_handle": "CheapMaineLobster", "web": None},
    {"name": "Pine Tree Seafood & Produce", "location": "Scarborough", "fb_handle": "PineTreeSeafood", "web": "https://pinetreeseafood.com/shop"},
    {"name": "Harbor Fish Market", "location": "Portland + Scarborough", "fb_handle": "harborfishmarket", "web": "https://harborfish.com/product-category/all/lobster/live-lobster/"},
    {"name": "Harbor Fish Market (Oysters)", "location": "Portland + Scarborough", "fb_handle": "harborfishmarket", "web": "https://harborfish.com/product-category/all/shellfish/oysters/"},
    {"name": "Free Range Fish & Lobster", "location": "Portland", "fb_handle": "freerangefishandlobster", "web": None},
    {"name": "SoPo Seafood Market & Raw Bar", "location": "South Portland", "fb_handle": "soposeafood", "web": None},
]


def _load_fb_cookies() -> str | None:
    """Load FB session cookies string for facebook-scraper."""
    if not FB_COOKIES_FILE.exists():
        return None
    try:
        raw = FB_COOKIES_FILE.read_text(encoding="utf-8").strip()
        if not raw:
            return None
        data = json.loads(raw)
        if isinstance(data, str):
            return data
        if isinstance(data, list):
            return "; ".join(f"{c['name']}={c['value']}" for c in data if c.get("name"))
        if isinstance(data, dict) and "cookies" in data:
            return data["cookies"]
        return None
    except json.JSONDecodeError:
        return FB_COOKIES_FILE.read_text(encoding="utf-8").strip() or None


def _search_fallback(market: dict, *, num: int = 5) -> list[dict]:
    """Google CSE → DDG fallback chain with specials-aware queries."""
    import time as _time
    from google_cse import is_configured, search_fb_posts as cse_search
    from ddg_search import search_fb_posts as ddg_search

    results: list[dict] = []
    if is_configured():
        results = cse_search(market["name"], market["fb_handle"], num=num)
        if results:
            print(f"  [google-cse] {market['name']}: {len(results)} results", flush=True)
    if not results:
        results = ddg_search(market["name"], market["fb_handle"], num=num)
        if not results:
            print(f"  [ddg retry after 10s] {market['name']}", flush=True)
            _time.sleep(10)
            results = ddg_search(market["name"], market["fb_handle"], num=num)
        if results:
            print(f"  [duckduckgo] {market['name']}: {len(results)} results", flush=True)
    return results


def _scrape_market(market: dict) -> list[dict]:
    """Pull latest posts. FB (with cookies) → CSE → DDG fallback chain."""
    from facebook_scraper import get_posts

    results: list[dict] = []
    fb_error: str | None = None
    cookies = _load_fb_cookies()
    scrape_kwargs: dict = {
        "pages": 3,
        "options": {"allow_extra_requests": False},
        "timeout": 60,
    }
    if cookies:
        scrape_kwargs["cookies"] = cookies

    try:
        posts_iter = get_posts(market["fb_handle"], **scrape_kwargs)
        for p in posts_iter:
            if not p:
                continue
            post_id = p.get("post_id") or p.get("post_url", "").rstrip("/").split("/")[-1]
            text = p.get("text") or p.get("post_text") or ""
            ts = p.get("time")
            url = p.get("post_url") or p.get("link") or ""
            results.append({
                "market": market["name"],
                "post_id": str(post_id),
                "timestamp": ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
                "text": text,
                "url": url,
                "source": "facebook",
                "source_quality": source_quality_score("facebook"),
            })
            if len(results) >= 10:
                break
    except Exception as e:
        fb_error = f"{type(e).__name__}: {e}"
        print(f"  [fb scrape error] {market['fb_handle']}: {fb_error}", file=sys.stderr)

    if not results:
        results = _search_fallback(market, num=5)
        if not results and fb_error is None:
            print(f"  [no results for {market['name']}]", flush=True)
    return results


def _scrape_web(market: dict) -> list[dict]:
    url = market.get("web")
    if not url:
        return []
    import re as _re
    import urllib.request as _ur
    try:
        req = _ur.Request(url, headers={"User-Agent": "Mozilla/5.0 (lobster-monitor)"})
        with _ur.urlopen(req, timeout=30) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"  [web scrape error] {market['name']}: {type(e).__name__}: {e}", file=sys.stderr)
        return []

    from parse_web import parse_web_catalog
    structured = parse_web_catalog(html)
    text = _re.sub(r"<[^>]+>", " ", html)
    text = _re.sub(r"\s+", " ", text).strip()[:4000]
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    post_id = f"web-{market['fb_handle']}-{day}"
    return [{
        "market": market["name"],
        "post_id": post_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "text": text,
        "url": url,
        "source": "web",
        "source_quality": source_quality_score("web"),
        "structured_prices": structured,
    }]


def _process_gated_rows(
    gated_passed: list,
    quarantined: list,
    market: dict,
    p: dict,
    observed_at: str,
    run_stats: dict,
) -> list[dict]:
    """Persist gated rows and fire threshold alerts. Returns passed special items."""
    special_items: list[dict] = []
    for g in gated_passed:
        append_jsonl("prices.jsonl", {
            "market": market["name"],
            "observed_at": observed_at,
            "post_id": p["post_id"],
            "kind": g.kind,
            "key": g.key,
            "price": g.price,
            "unit": g.unit,
            "snippet": g.snippet,
            "confidence": g.confidence,
            "source_quality": g.source_quality,
            "gate_passed": True,
            "source": p.get("source", "unknown"),
        })
        if g.kind == "special":
            special_items.append({
                "key": g.key, "price": g.price, "unit": g.unit,
                "confidence": g.confidence,
            })
        if g.kind == "lobster_tier" and g.key in LOBSTER_TIER_THRESHOLDS:
            threshold = LOBSTER_TIER_THRESHOLDS[g.key]
            if g.price < threshold:
                if alert_lobster_drop(
                    market["name"], g.key, g.price, p["url"], observed_at,
                    threshold, confidence=g.confidence,
                ):
                    run_stats["lobster_alerts"] += 1
        if g.kind == "oyster_tier" and g.key in OYSTER_TIER_THRESHOLDS:
            threshold = OYSTER_TIER_THRESHOLDS[g.key]
            if g.unit == "doz":
                if g.price < threshold:
                    if alert_oyster_drop(
                        market["name"], g.key, g.price, p["url"], observed_at,
                        threshold, g.unit, confidence=g.confidence,
                    ):
                        run_stats["oyster_alerts"] += 1
            elif g.unit == "lb":
                lb_threshold = threshold / 12.0
                if g.price < lb_threshold:
                    if alert_oyster_drop(
                        market["name"], g.key, g.price, p["url"], observed_at,
                        lb_threshold, g.unit, confidence=g.confidence,
                    ):
                        run_stats["oyster_alerts"] += 1

    for g in quarantined:
        append_jsonl("quarantine.jsonl", {
            "market": market["name"],
            "observed_at": observed_at,
            "post_id": p["post_id"],
            "kind": g.kind,
            "key": g.key,
            "price": g.price,
            "unit": g.unit,
            "snippet": g.snippet,
            "confidence": g.confidence,
            "source_quality": g.source_quality,
            "reject_reason": g.reject_reason,
            "source": p.get("source", "unknown"),
        })
        run_stats["rows_quarantined"] += 1

    run_stats["rows_gated"] += len(gated_passed) + len(quarantined)
    if gated_passed:
        run_stats["confidence_sum"] += sum(g.confidence for g in gated_passed)
        run_stats["confidence_count"] += len(gated_passed)
    return special_items


def main() -> int:
    started = datetime.now(timezone.utc).isoformat()
    print(f"[{started}] lobster-price-monitor: starting", flush=True)

    run_stats: dict = {
        "ts": started,
        "markets_attempted": len(MARKETS),
        "markets_succeeded": 0,
        "posts_pulled": 0,
        "new_posts": 0,
        "prices_parsed": 0,
        "lobster_alerts": 0,
        "oyster_alerts": 0,
        "special_alerts": 0,
        "rows_gated": 0,
        "rows_quarantined": 0,
        "confidence_sum": 0,
        "confidence_count": 0,
        "avg_confidence": 0.0,
        "source_breakdown": {},
        "errors": [],
    }

    for market in MARKETS:
        print(f"  scraping {market['name']} ({market['fb_handle']})...", flush=True)
        posts = _scrape_market(market)
        web_posts = _scrape_web(market)
        if web_posts:
            posts = posts + web_posts
        if posts:
            run_stats["markets_succeeded"] += 1
        run_stats["posts_pulled"] += len(posts)
        for p in posts:
            src = p.get("source", "unknown")
            run_stats["source_breakdown"][src] = run_stats["source_breakdown"].get(src, 0) + 1
        run_stats["errors"].append({
            "market": market["name"],
            "fb_handle": market["fb_handle"],
            "fetched": len(posts),
        })

        seen = seen_post_ids("history.jsonl", market["name"])
        new_posts = [p for p in posts if p["post_id"] not in seen]
        run_stats["new_posts"] += len(new_posts)
        print(f"    fetched {len(posts)} posts, {len(new_posts)} new", flush=True)

        for p in posts:
            row = dict(p)
            if "source_quality" not in row:
                row["source_quality"] = source_quality_score(p.get("source", "unknown"))
            append_jsonl("history.jsonl", row)

        for p in new_posts:
            observed_at = p["timestamp"]
            source = p.get("source", "unknown")
            full_text = p.get("text", "")

            if "structured_prices" in p:
                parsed = [tuple(sp) for sp in p["structured_prices"]]
                meta = [{"price_pos": 0, "bare_price": False}] * len(parsed)
            else:
                parsed, meta = parse_post_with_meta(full_text)

            run_stats["prices_parsed"] += len(parsed)
            passed, quarantined = gate_rows(
                parsed, source=source, observed_at=observed_at,
                full_text=full_text, parse_meta=meta,
            )
            special_items = _process_gated_rows(
                passed, quarantined, market, p, observed_at, run_stats,
            )

            # AC4b specials alert for FB/search posts
            if "structured_prices" not in p:
                gated_specials = [s for s in special_items if s.get("confidence", 0) >= 70]
                if gated_specials and is_specials_post(full_text):
                    if alert_specials_post(
                        market["name"], p["url"], full_text, observed_at,
                        special_items=gated_specials, source=source,
                    ):
                        run_stats["special_alerts"] += 1
            else:
                # Web catalog specials diff alerting
                current_specials = {
                    (g.key, g.price, g.unit) for g in passed if g.kind == "special"
                }
                prev_specials = last_web_specials(market["name"])
                new_special_rows = current_specials - prev_specials
                if new_special_rows:
                    new_items = [
                        {"key": k, "price": pr, "unit": u, "confidence": g.confidence}
                        for g in passed if g.kind == "special"
                        for k, pr, u in [(g.key, g.price, g.unit)]
                        if (k, pr, u) in new_special_rows and g.confidence >= 70
                    ]
                    if new_items and alert_web_specials(
                        market["name"], p["url"], observed_at, new_items,
                    ):
                        run_stats["special_alerts"] += 1
                save_web_snapshot(market["name"], [
                    {"key": g.key, "price": g.price, "unit": g.unit}
                    for g in passed if g.kind == "special"
                ])

        time.sleep(5)

    if run_stats["confidence_count"]:
        run_stats["avg_confidence"] = round(
            run_stats["confidence_sum"] / run_stats["confidence_count"], 1,
        )
    append_jsonl("run-log.jsonl", run_stats)

    try:
        from board_render import write_html_board
        board_path = write_html_board()
        print(f"  [board] wrote {board_path}", flush=True)
    except Exception as e:
        print(f"  [board error] {type(e).__name__}: {e}", file=sys.stderr)

    finished = datetime.now(timezone.utc).isoformat()
    print(
        f"[{finished}] done. {run_stats['markets_succeeded']}/{run_stats['markets_attempted']} markets, "
        f"{run_stats['new_posts']} new posts, {run_stats['prices_parsed']} prices, "
        f"{run_stats['rows_quarantined']} quarantined, avg conf {run_stats['avg_confidence']}, "
        f"{run_stats['lobster_alerts']} lobster, {run_stats['oyster_alerts']} oyster, "
        f"{run_stats['special_alerts']} specials alerts",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
