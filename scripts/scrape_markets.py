#!/usr/bin/env python3
"""Main entrypoint: scrape markets, parse prices, gate, alert.

Run: python3 scripts/scrape_markets.py
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from secrets import load_fb_cookies

from markets import MARKETS
from parse_prices import is_specials_post, parse_post, parse_post_with_meta
from quality_gate import gate_rows, source_quality_score
from send_alert import (
    alert_lobster_drop,
    alert_oyster_drop,
    alert_specials_post,
    alert_web_specials,
    begin_alert_run,
)
from state import (
    PARSER_VERSION,
    append_jsonl,
    append_jsonl_deduped,
    build_history_post_index,
    count_passed_rows_by_market,
    ensure_logs_dir,
    last_web_specials,
    persist_key,
    read_jsonl,
    recent_history_posts,
    save_web_snapshot,
    write_json,
)

logger = logging.getLogger(__name__)

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


def _load_fb_cookies() -> dict[str, str] | str | None:
    """Load FB session cookies for facebook-scraper (dict, file path, or 'from_browser')."""
    return load_fb_cookies()


def _search_fallback(market: dict, *, num: int = 5) -> tuple[list[dict], str | None]:
    """Google CSE → DDG fallback chain with specials-aware queries."""
    if _load_fb_cookies():
        return [], "facebook_auth_required_no_cookies"
    import time as _time

    from ddg_search import search_fb_posts as ddg_search
    from google_cse import is_configured
    from google_cse import search_fb_posts as cse_search

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
    if not results:
        return [], "duckduckgo_captcha_or_no_results"
    return results, None


def _scrape_market(market: dict) -> tuple[list[dict], str | None]:
    """Pull latest posts. Authenticated curl → facebook-scraper → CSE → DDG."""
    results: list[dict] = []
    fb_error: str | None = None
    cookies = _load_fb_cookies()

    if cookies:
        try:
            from fb_curl_fetch import fetch_fb_posts
            from quality_gate import source_quality_score

            curl_posts = fetch_fb_posts(
                market["name"],
                market["fb_handle"],
                max_posts=10,
            )
            if curl_posts:
                print(f"  [fb curl] {market['name']}: {len(curl_posts)} posts", flush=True)
                for p in curl_posts:
                    p["source_quality"] = source_quality_score(p.get("source", "facebook"))
                results = curl_posts
        except Exception as e:
            fb_error = f"{type(e).__name__}: {e}"
            print(f"  [fb curl error] {market['fb_handle']}: {fb_error}", file=sys.stderr)

    if not results and cookies:
        from facebook_scraper import get_posts

        scrape_kwargs: dict = {
            "pages": 3,
            "options": {"allow_extra_requests": False},
            "timeout": 60,
            "cookies": cookies,
        }
        try:
            posts_iter = get_posts(market["fb_handle"], **scrape_kwargs)
            for p in posts_iter:
                if not p:
                    continue
                post_id = p.get("post_id") or p.get("post_url", "").rstrip("/").split("/")[-1]
                text = p.get("text") or p.get("post_text") or ""
                ts = p.get("time")
                url = p.get("post_url") or p.get("link") or ""
                results.append(
                    {
                        "market": market["name"],
                        "post_id": str(post_id),
                        "timestamp": ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
                        "text": text,
                        "url": url,
                        "source": "facebook",
                        "source_quality": source_quality_score("facebook"),
                    }
                )
                if len(results) >= 10:
                    break
            if results:
                print(f"  [facebook-scraper] {market['name']}: {len(results)} posts", flush=True)
        except Exception as e:
            fb_error = fb_error or f"{type(e).__name__}: {e}"
            print(f"  [fb scrape error] {market['fb_handle']}: {fb_error}", file=sys.stderr)

    if not results:
        if cookies:
            if fb_error:
                return [], f"facebook_fetch_failed:{fb_error}"
            return [], "no_posts_from_facebook"
        results, search_blocker = _search_fallback(market, num=5)
        if not results:
            if search_blocker:
                return [], search_blocker
            if fb_error:
                return [], f"facebook_fetch_failed:{fb_error}"
            return [], "facebook_auth_required_no_cookies"
        if not results and fb_error is None:
            print(f"  [no results for {market['name']}]", flush=True)
    return results, None


def _scrape_web_url(market: dict, url: str, *, slug_suffix: str = "") -> dict | None:
    import re as _re
    import urllib.request as _ur

    try:
        req = _ur.Request(url, headers={"User-Agent": "Mozilla/5.0 (lobster-monitor)"})
        with _ur.urlopen(req, timeout=30) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(
            f"  [web scrape error] {market['name']} ({url}): {type(e).__name__}: {e}",
            file=sys.stderr,
        )
        return None

    from parse_web import parse_web_catalog_rows

    structured_rows = parse_web_catalog_rows(html)
    structured = [row.as_parsed_tuple() for row in structured_rows]
    text = _re.sub(r"<[^>]+>", " ", html)
    text = _re.sub(r"\s+", " ", text).strip()[:4000]
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    handle = market["fb_handle"]
    post_id = f"web-{handle}{slug_suffix}-{day}"
    return {
        "market": market["name"],
        "post_id": post_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "text": text,
        "url": url,
        "source": "web",
        "source_quality": source_quality_score("web"),
        "structured_prices": structured,
        "structured_meta": [row.persist_metadata() for row in structured_rows],
    }


def _scrape_reference(market: dict) -> dict | None:
    """Fetch reference menu URL and parse lobster prices from page text."""
    import re as _re
    import urllib.request as _ur

    url = market.get("reference_url")
    if not url:
        return None
    try:
        req = _ur.Request(url, headers={"User-Agent": "Mozilla/5.0 (lobster-monitor)"})
        with _ur.urlopen(req, timeout=30) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(
            f"  [reference scrape error] {market['name']}: {type(e).__name__}: {e}", file=sys.stderr
        )
        return None

    text = _re.sub(r"<[^>]+>", " ", html)
    text = _re.sub(r"\s+", " ", text).strip()[:8000]

    parsed = parse_post(text)
    lobster_rows = [r for r in parsed if r[0] == "lobster_tier"]
    if not lobster_rows:
        return None
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    handle = market["fb_handle"]
    return {
        "market": market["name"],
        "post_id": f"ref-{handle}-{day}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "text": text,
        "url": url,
        "source": "reference",
        "source_quality": source_quality_score("web"),
    }


def _scrape_web(market: dict) -> list[dict]:
    urls: list[tuple[str, str]] = []
    primary = market.get("web")
    if primary:
        urls.append((primary, ""))
    for i, extra in enumerate(market.get("web_extra") or []):
        urls.append((extra, f"-extra{i}"))
    if not urls:
        ref_post = _scrape_reference(market)
        return [ref_post] if ref_post else []

    posts: list[dict] = []
    for url, slug_suffix in urls:
        post = _scrape_web_url(market, url, slug_suffix=slug_suffix)
        if post and post.get("structured_prices"):
            posts.append(post)
    ref_post = _scrape_reference(market)
    if ref_post:
        posts.append(ref_post)
    return posts


def _record_suppressed_alert(
    run_stats: dict,
    *,
    kind: str,
    market: str,
    detail: str,
    url: str = "",
) -> None:
    run_stats["alerts_suppressed"] += 1
    entry = {"kind": kind, "market": market, "detail": detail, "url": url}
    run_stats["alerts_suppressed_opportunities"].append(entry)
    run_stats["alerts_suppressed_detail"].append(f"{market}:{detail}")


def _process_gated_rows(
    gated_passed: list,
    quarantined: list,
    market: dict,
    p: dict,
    observed_at: str,
    run_stats: dict,
    *,
    send_alerts: bool,
    persist_seen: set[str],
    cumulative_passed: dict[str, int],
    web_meta: list[dict] | None = None,
    structured_prices: list | None = None,
) -> list[dict]:
    """Persist gated rows and fire threshold alerts. Returns passed special items."""
    special_items: list[dict] = []
    web_meta = web_meta or []
    meta_lookup: dict[tuple, dict] = {}
    if structured_prices:
        for sp, meta in zip(structured_prices, web_meta):
            meta_lookup[(sp[0], sp[1], float(sp[2]), sp[3])] = meta
    for g in gated_passed:
        row = {
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
            "source_url": p.get("url", ""),
            "fetch_timestamp": observed_at,
            "parser_version": PARSER_VERSION,
            "gate_details": {
                "gate_a": g.gate_a_passed,
                "gate_b": g.gate_b_passed,
                "gate_c": g.gate_c_passed,
                "raw_confidence": g.raw_confidence,
            },
        }
        meta = meta_lookup.get((g.kind, g.key, float(g.price), g.unit), {})
        if meta:
            meta = dict(meta)
            if meta.get("price_high") is not None:
                meta["raw_price_high"] = meta["price_high"]
            if meta.get("price_display_type") == "range":
                meta["price_is_range"] = True
            if meta.get("normalization_weight_lb") is not None:
                meta["normalization_weight"] = meta["normalization_weight_lb"]
            row.update(meta)
        if append_jsonl_deduped("prices.jsonl", row, seen=persist_seen):
            run_stats["rows_persisted"] = run_stats.get("rows_persisted", 0) + 1
            cumulative_passed[market["name"]] = cumulative_passed.get(market["name"], 0) + 1
        else:
            run_stats["rows_deduped"] = run_stats.get("rows_deduped", 0) + 1
        if g.kind == "special":
            special_items.append(
                {
                    "key": g.key,
                    "price": g.price,
                    "unit": g.unit,
                    "confidence": g.confidence,
                }
            )
        if g.kind == "lobster_tier" and g.key in LOBSTER_TIER_THRESHOLDS:
            threshold = LOBSTER_TIER_THRESHOLDS[g.key]
            if g.price < threshold:
                if not send_alerts:
                    _record_suppressed_alert(
                        run_stats,
                        kind="lobster_tier",
                        market=market["name"],
                        detail=f"{g.key}@${g.price:.2f}<${threshold:.2f}",
                        url=p.get("url", ""),
                    )
                elif alert_lobster_drop(
                    market["name"],
                    g.key,
                    g.price,
                    p["url"],
                    observed_at,
                    threshold,
                    confidence=g.confidence,
                ):
                    run_stats["lobster_alerts"] = run_stats.get("lobster_alerts", 0) + 1
        if g.kind == "oyster_tier" and g.key in OYSTER_TIER_THRESHOLDS:
            threshold = OYSTER_TIER_THRESHOLDS[g.key]
            if g.unit == "doz":
                if g.price < threshold:
                    if not send_alerts:
                        _record_suppressed_alert(
                            run_stats,
                            kind="oyster_tier",
                            market=market["name"],
                            detail=f"{g.key}@${g.price:.2f}<${threshold:.2f}/doz",
                            url=p.get("url", ""),
                        )
                    elif alert_oyster_drop(
                        market["name"],
                        g.key,
                        g.price,
                        p["url"],
                        observed_at,
                        threshold,
                        g.unit,
                        confidence=g.confidence,
                    ):
                        run_stats["oyster_alerts"] += 1
            elif g.unit == "lb":
                lb_threshold = threshold / 12.0
                if g.price < lb_threshold:
                    if not send_alerts:
                        _record_suppressed_alert(
                            run_stats,
                            kind="oyster_tier",
                            market=market["name"],
                            detail=f"{g.key}@${g.price:.2f}<${lb_threshold:.2f}/lb",
                            url=p.get("url", ""),
                        )
                    elif alert_oyster_drop(
                        market["name"],
                        g.key,
                        g.price,
                        p["url"],
                        observed_at,
                        lb_threshold,
                        g.unit,
                        confidence=g.confidence,
                    ):
                        run_stats["oyster_alerts"] += 1

    for g in quarantined:
        append_jsonl(
            "quarantine.jsonl",
            {
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
            },
        )
        run_stats["rows_quarantined"] = run_stats.get("rows_quarantined", 0) + 1

    run_stats["rows_gated"] = run_stats.get("rows_gated", 0) + len(gated_passed) + len(quarantined)
    if gated_passed:
        run_stats["confidence_sum"] = run_stats.get("confidence_sum", 0) + sum(
            g.confidence for g in gated_passed
        )
        run_stats["confidence_count"] = run_stats.get("confidence_count", 0) + len(gated_passed)
    return special_items


def _setup_run_logging(started: str) -> Path:
    logs_dir = ensure_logs_dir()
    log_path = logs_dir / f"scrape-{started[:10]}.log"
    return log_path


def _log_line(log_path: Path, message: str) -> None:
    with log_path.open("a", encoding="utf-8") as f:
        f.write(message.rstrip() + "\n")


def main(*, send_alerts: bool = False) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    start_time = time.time()
    started = datetime.now(timezone.utc).isoformat()
    log_path = _setup_run_logging(started)
    logger.info("lobster-price-monitor: starting alerts=%s", send_alerts)
    print(f"[{started}] lobster-price-monitor: starting", flush=True)
    _log_line(log_path, f"[{started}] lobster-price-monitor: starting alerts={send_alerts}")

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
        "alerts_enabled": send_alerts,
        "alerts_suppressed": 0,
        "alerts_suppressed_opportunities": [],
        "alerts_suppressed_detail": [],
        "rows_persisted": 0,
        "rows_deduped": 0,
        "rows_gated": 0,
        "market_status": [],
        "rows_quarantined": 0,
        "confidence_sum": 0,
        "confidence_count": 0,
        "avg_confidence": 0.0,
        "source_breakdown": {},
        "errors": [],
        "market_coverage": [],
    }
    existing_prices = read_jsonl("prices.jsonl")
    persist_seen = {persist_key(r) for r in existing_prices}
    cumulative_passed = count_passed_rows_by_market(existing_prices)
    history_index = build_history_post_index()
    if send_alerts:
        begin_alert_run()
    coverage_entries: list[dict] = []

    for market in MARKETS:
        logger.info("scraping %s (%s)", market["name"], market["fb_handle"])
        print(f"  scraping {market['name']} ({market['fb_handle']})...", flush=True)
        _log_line(log_path, f"scraping {market['name']}")
        posts, fb_blocker = _scrape_market(market)
        web_posts = _scrape_web(market)
        if web_posts:
            posts = posts + web_posts
        if not posts and not market.get("web"):
            hist = recent_history_posts(market["name"], max_age_days=7, limit=5)
            if hist:
                posts = hist
                print(f"    [history fallback] {len(posts)} recent post(s)", flush=True)
        market_passed = 0
        if posts:
            run_stats["markets_succeeded"] += 1
        run_stats["posts_pulled"] += len(posts)
        for p in posts:
            src = p.get("source", "unknown")
            run_stats["source_breakdown"][src] = run_stats["source_breakdown"].get(src, 0) + 1

        source_used = posts[0].get("source") if posts else None
        blocker = fb_blocker
        if not posts and market.get("web") and not web_posts:
            blocker = blocker or "web_fetch_failed_or_empty_catalog"
        if not posts and not blocker:
            blocker = "no_posts_from_configured_sources"

        market_name = market["name"]
        if not posts and blocker:
            logger.warning("%s blocked: %s", market_name, blocker)

        run_stats["errors"].append(
            {
                "market": market_name,
                "fb_handle": market["fb_handle"],
                "fetched": len(posts),
                "blocker": blocker,
                "source_used": source_used,
            }
        )

        seen = history_index.get(market_name, set())
        new_posts = [p for p in posts if p["post_id"] not in seen]
        # Web catalogs change intraday — always re-parse structured prices.
        posts_to_price = [
            p
            for p in posts
            if p["post_id"] not in seen
            or "structured_prices" in p
            or p.get("source") in ("facebook", "facebook_search", "reference")
        ]
        run_stats["new_posts"] += len(new_posts)
        print(f"    fetched {len(posts)} posts, {len(new_posts)} new", flush=True)

        for p in posts:
            post_id = str(p["post_id"])
            if post_id in seen:
                continue
            row = dict(p)
            if "source_quality" not in row:
                row["source_quality"] = source_quality_score(p.get("source", "unknown"))
            append_jsonl("history.jsonl", row)
            seen.add(post_id)
            history_index.setdefault(market_name, set()).add(post_id)

        for p in posts_to_price:
            observed_at = p["timestamp"]
            source = p.get("source", "unknown")
            full_text = p.get("text", "")

            if "structured_prices" in p:
                parsed = [tuple(sp) for sp in p["structured_prices"]]
                meta = [
                    {"price_pos": None, "bare_price": False, "structured": True} for _ in parsed
                ]
            else:
                parsed, meta = parse_post_with_meta(full_text)

            run_stats["prices_parsed"] += len(parsed)
            passed, quarantined = gate_rows(
                parsed,
                source=source,
                observed_at=observed_at,
                full_text=full_text,
                parse_meta=meta,
            )
            special_items = _process_gated_rows(
                passed,
                quarantined,
                market,
                p,
                observed_at,
                run_stats,
                send_alerts=send_alerts,
                persist_seen=persist_seen,
                cumulative_passed=cumulative_passed,
                web_meta=p.get("structured_meta"),
                structured_prices=p.get("structured_prices"),
            )
            market_passed += len(passed)

            # AC4b specials alert for FB/search posts
            if "structured_prices" not in p:
                gated_specials = [s for s in special_items if s.get("confidence", 0) >= 70]
                if gated_specials and is_specials_post(full_text):
                    if not send_alerts:
                        _record_suppressed_alert(
                            run_stats,
                            kind="special",
                            market=market["name"],
                            detail=f"specials_post:{len(gated_specials)}_items",
                            url=p.get("url", ""),
                        )
                    elif alert_specials_post(
                        market["name"],
                        p["url"],
                        full_text,
                        observed_at,
                        special_items=gated_specials,
                        source=source,
                    ):
                        run_stats["special_alerts"] += 1
            else:
                # Web catalog specials diff alerting
                current_specials = {(g.key, g.price, g.unit) for g in passed if g.kind == "special"}
                prev_specials = last_web_specials(market["name"])
                new_special_rows = current_specials - prev_specials
                if new_special_rows:
                    new_items = [
                        {"key": k, "price": pr, "unit": u, "confidence": g.confidence}
                        for g in passed
                        if g.kind == "special"
                        for k, pr, u in [(g.key, g.price, g.unit)]
                        if (k, pr, u) in new_special_rows and g.confidence >= 70
                    ]
                    if new_items:
                        if not send_alerts:
                            _record_suppressed_alert(
                                run_stats,
                                kind="web_special",
                                market=market["name"],
                                detail=f"new_web_specials:{len(new_items)}",
                                url=p.get("url", ""),
                            )
                        elif alert_web_specials(
                            market["name"],
                            p["url"],
                            observed_at,
                            new_items,
                        ):
                            run_stats["special_alerts"] += 1
                save_web_snapshot(
                    market["name"],
                    [
                        {"key": g.key, "price": g.price, "unit": g.unit}
                        for g in passed
                        if g.kind == "special"
                    ],
                )

        cumulative_passed_count = cumulative_passed.get(market_name, 0)
        has_live_data = market_passed > 0 or cumulative_passed_count > 0
        if has_live_data:
            status = "live"
            market_blocker = None
        elif posts:
            status = "partial"
            market_blocker = blocker or "fetched_but_no_passed_rows"
        else:
            status = "blocked"
            market_blocker = blocker or "no_posts_from_configured_sources"

        entry = {
            "market": market["name"],
            "name": market["name"],
            "posts_fetched": len(posts),
            "passed_rows": market_passed,
            "cumulative_passed_rows": cumulative_passed_count,
            "source_used": source_used,
            "blocker": market_blocker,
            "status": status,
        }
        coverage_entries.append(entry)
        run_stats["market_status"].append(entry)
        time.sleep(2)

    run_stats["market_coverage"] = coverage_entries
    write_json(
        "market-coverage.json",
        {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "markets": coverage_entries,
        },
    )

    if run_stats["confidence_count"]:
        run_stats["avg_confidence"] = round(
            run_stats["confidence_sum"] / run_stats["confidence_count"],
            1,
        )
    run_stats["duration_seconds"] = round(time.time() - start_time, 2)
    append_jsonl("run-log.jsonl", run_stats)
    _log_line(log_path, json.dumps(run_stats, ensure_ascii=False))

    try:
        from board_render import write_html_board

        board_path = write_html_board()
        print(f"  [board] wrote {board_path}", flush=True)
    except Exception as e:
        print(f"  [board error] {type(e).__name__}: {e}", file=sys.stderr)

    try:
        from state import compact_prices_jsonl, rotate_state_files

        kept = compact_prices_jsonl(min_confidence=0)
        print(f"  [compact] prices.jsonl → {kept} rows", flush=True)
        rotate_state_files(max_days=90)
        print("  [rotate] completed log rotation for state files", flush=True)
    except Exception as e:
        print(f"  [compact error] {type(e).__name__}: {e}", file=sys.stderr)

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


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scrape seafood markets and update the board")
    alert_group = parser.add_mutually_exclusive_group()
    alert_group.add_argument(
        "--alerts",
        action="store_true",
        help="Send Telegram alerts when thresholds are met (off by default)",
    )
    alert_group.add_argument(
        "--no-alerts",
        action="store_true",
        help="Explicitly suppress Telegram alerts (default behavior)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    sys.exit(main(send_alerts=args.alerts))
