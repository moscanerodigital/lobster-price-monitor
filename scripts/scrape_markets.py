#!/usr/bin/env python3
"""Main entrypoint: scrape 5 FB markets, parse prices, send alerts.

Run: /Users/openclaw/.hermes/hermes-agent/venv/bin/python3 scripts/scrape_markets.py
"""
from __future__ import annotations
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Make sibling imports work
sys.path.insert(0, str(Path(__file__).resolve().parent))

from state import append_jsonl, read_jsonl, seen_post_ids
from parse_prices import parse_post
from send_alert import alert_lobster_drop, alert_oyster_drop, alert_special

# Thresholds (editable per README)
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

# Oyster thresholds (editable) — Erik likes oysters, so we alert on a deal
OYSTER_TIER_THRESHOLDS = {
    "xl": 28.00,              # $XL doz — alert if < $28/doz
    "jumbo": 26.00,
    "select": 22.00,
    "standard": 18.00,
    "single_select": 32.00,
    "named_variety": 24.00,   # Wellfleet, Blue Point, Beausoleil, etc.
    "small": 18.00,
    "medium": 20.00,
    "large": 24.00,
    "pint": 30.00,
    "oyster": 22.00,          # generic fallback
}

# Markets to scrape
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


def _scrape_market(market: dict) -> list[dict]:
    """Pull latest posts from a single market. Returns list of normalized dicts.
    Never raises — errors are caught and returned as [].

    Source priority:
    1. Facebook public page (via facebook-scraper) — works only with cookies
    2. DuckDuckGo HTML search fallback (site:facebook.com/<handle>) — works
       unauthenticated, returns indexed post snippets. Rate-limited (DDG
       captcha after rapid requests), so we add a small delay + 1 retry.
    Either way the post text is run through the standard parse_prices pipeline."""
    import time as _time
    from facebook_scraper import get_posts  # imported lazily
    results: list[dict] = []
    fb_error: str | None = None
    try:
        posts_iter = get_posts(
            market["fb_handle"],
            pages=3,
            options={"allow_extra_requests": False},
            timeout=60,
        )
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
            })
            if len(results) >= 10:
                break
    except Exception as e:
        fb_error = f"{type(e).__name__}: {e}"
        print(f"  [fb scrape error] {market['fb_handle']}: {fb_error}", file=sys.stderr)

    # If FB returned 0 results, fall back to DuckDuckGo search
    if not results:
        from ddg_search import search_fb_posts
        # First attempt
        gcs = search_fb_posts(market["name"], market["fb_handle"], num=5)
        if gcs:
            results = gcs
        else:
            # Wait + 1 retry — DDG captcha clears in ~10s for legit-browser-rate requests
            print(f"  [ddg retry after 10s] {market['name']}", flush=True)
            _time.sleep(10)
            gcs = search_fb_posts(market["name"], market["fb_handle"], num=5)
            if gcs:
                results = gcs
            elif fb_error:
                pass  # already printed
        if not results and fb_error is None:
            print(f"  [no results for {market['name']}]", flush=True)
    return results


def _scrape_web(market: dict) -> list[dict]:
    """If a market has a structured web catalog, scrape + parse it. Returns list of normalized dicts.
    Per-market failures logged, never raise.

    Note: the web catalog is parsed into structured rows, not raw text —
    so we return both a 'text' (full page text) for the history AND individual
    price rows for the prices.jsonl. The post_id is a stable day-keyed
    synthetic ID so dedup works daily."""
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

    # Parse structured products
    from parse_web import parse_web_catalog  # type: ignore
    structured = parse_web_catalog(html)
    # Also keep raw text snippet
    text = _re.sub(r"<[^>]+>", " ", html)
    text = _re.sub(r"\s+", " ", text).strip()[:4000]
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    post_id = f"web-{market['fb_handle']}-{day}"
    # Return as a single 'post' that has a structured marker — scrape_markets main
    # loop will look for 'structured_prices' field to add prices directly.
    return [{
        "market": market["name"],
        "post_id": post_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "text": text,
        "url": url,
        "source": "web",
        "structured_prices": structured,  # list of (kind, key, price, unit, snippet)
    }]


def main() -> int:
    started = datetime.now(timezone.utc).isoformat()
    print(f"[{started}] lobster-price-monitor: starting", flush=True)

    run_stats = {
        "ts": started,
        "markets_attempted": len(MARKETS),
        "markets_succeeded": 0,
        "posts_pulled": 0,
        "new_posts": 0,
        "prices_parsed": 0,
        "lobster_alerts": 0,
        "oyster_alerts": 0,
        "special_alerts": 0,
        "errors": [],
    }

    for market in MARKETS:
        print(f"  scraping {market['name']} ({market['fb_handle']})...", flush=True)
        posts = _scrape_market(market)
        # Also scrape web catalog if available
        web_posts = _scrape_web(market)
        if web_posts:
            posts = posts + web_posts
        if posts:
            run_stats["markets_succeeded"] += 1
        run_stats["posts_pulled"] += len(posts)
        run_stats["errors"].append({
            "market": market["name"],
            "fb_handle": market["fb_handle"],
            "fetched": len(posts),
        })

        # Dedup: only process posts we haven't seen for this market
        seen = seen_post_ids("history.jsonl", market["name"])
        new_posts = [p for p in posts if p["post_id"] not in seen]
        run_stats["new_posts"] += len(new_posts)
        print(f"    fetched {len(posts)} posts, {len(new_posts)} new", flush=True)

        # Persist all fetched posts to history (so we have full record)
        for p in posts:
            append_jsonl("history.jsonl", p)

        # Parse + alert on new posts only
        for p in new_posts:
            observed_at = p["timestamp"]
            # If this is a web-sourced post with structured_prices, use those
            if "structured_prices" in p:
                parsed = [tuple(sp) for sp in p["structured_prices"]]
            else:
                parsed = parse_post(p["text"])
            run_stats["prices_parsed"] += len(parsed)
            # Persist parsed prices
            for kind, key, price, unit, snippet in parsed:
                append_jsonl("prices.jsonl", {
                    "market": market["name"],
                    "observed_at": observed_at,
                    "post_id": p["post_id"],
                    "kind": kind,
                    "key": key,
                    "price": price,
                    "unit": unit,
                    "snippet": snippet,
                })
                if kind == "lobster_tier" and key in LOBSTER_TIER_THRESHOLDS:
                    threshold = LOBSTER_TIER_THRESHOLDS[key]
                    if price < threshold:
                        if alert_lobster_drop(market["name"], key, price, p["url"], observed_at, threshold):
                            run_stats["lobster_alerts"] += 1
                if kind == "oyster_tier" and key in OYSTER_TIER_THRESHOLDS:
                    threshold = OYSTER_TIER_THRESHOLDS[key]
                    # Oyster thresholds are typically per-dozen. If the
                    # actual unit is "lb" (live-in-shell by weight, common for
                    # wholesale markets), divide the doz threshold by 12 as
                    # a rough equivalent. Skip alerts for ambiguous cases.
                    if unit == "doz":
                        if price < threshold:
                            if alert_oyster_drop(market["name"], key, price, p["url"], observed_at, threshold, unit):
                                run_stats["oyster_alerts"] += 1
                    elif unit == "lb":
                        # Use 1/12 of the doz threshold as the per-lb ceiling
                        lb_threshold = threshold / 12.0
                        if price < lb_threshold:
                            if alert_oyster_drop(market["name"], key, price, p["url"], observed_at, lb_threshold, unit):
                                run_stats["oyster_alerts"] += 1
            # Specials alert (per new post) — only for FB posts with parsed prices
            if parsed and "structured_prices" not in p:
                if alert_special(market["name"], p["url"], p["text"], observed_at):
                    run_stats["special_alerts"] += 1

        # Be polite to FB/DDG — 5s delay between markets (DDG captcha triggers fast)
        time.sleep(5)

    append_jsonl("run-log.jsonl", run_stats)
    finished = datetime.now(timezone.utc).isoformat()
    print(f"[{finished}] done. {run_stats['markets_succeeded']}/{run_stats['markets_attempted']} markets, "
          f"{run_stats['new_posts']} new posts, {run_stats['prices_parsed']} prices, "
          f"{run_stats['lobster_alerts']} lobster alerts, {run_stats['oyster_alerts']} oyster alerts, "
          f"{run_stats['special_alerts']} specials alerts",
          flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
