#!/usr/bin/env python3
"""Generate fixtures/ci_gate_bplus/ seed data for Gate B+ CI verification."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "fixtures" / "ci_gate_bplus"
BASE = datetime(2026, 7, 5, 12, 0, 0, tzinfo=timezone.utc)

GATE_DETAILS = {"gate_a": True, "gate_b": True, "gate_c": True}
PARSER = "lobster-price-monitor/1.1"


def _ts(dt: datetime) -> str:
    return dt.isoformat()


def _row(
    *,
    market: str,
    post_id: str,
    kind: str,
    key: str,
    price: float,
    unit: str,
    snippet: str,
    confidence: int,
    source: str,
    source_url: str,
    observed_at: datetime,
    extra: dict | None = None,
) -> dict:
    row = {
        "market": market,
        "observed_at": _ts(observed_at),
        "post_id": post_id,
        "kind": kind,
        "key": key,
        "price": price,
        "unit": unit,
        "snippet": snippet,
        "confidence": confidence,
        "gate_passed": True,
        "source": source,
        "source_url": source_url,
        "fetch_timestamp": _ts(observed_at),
        "parser_version": PARSER,
        "gate_details": {**GATE_DETAILS, "raw_confidence": confidence},
    }
    if extra:
        row.update(extra)
    return row


def build_prices() -> list[dict]:
    rows: list[dict] = []
    today = BASE

    lobster_current = [
        (
            "Ancient Mariner Lobster Co.",
            "fb-amlobsterco-2026-07-05",
            "hard_shell",
            15.99,
            "hard shell live lobster $15.99/lb",
            90,
            "facebook",
            "https://facebook.com/amlobsterco/posts/1",
        ),
        (
            "Two Tides Seafood",
            "fb-twotides-2026-07-05",
            "1.125lb",
            7.99,
            "1 1/8 lb hard shell $7.99/lb",
            90,
            "facebook",
            "https://facebook.com/100054888565201/posts/1",
        ),
        (
            "Scarborough Fish & Lobster",
            "fb-scarborough-2026-07-05",
            "hard_shell",
            9.99,
            "hard shell $9.99/lb soft shell $10.99/lb",
            72,
            "facebook_search",
            "https://facebook.com/CheapMaineLobster/posts/1",
        ),
        (
            "Pine Tree Seafood & Produce",
            "web-pinetree-2026-07-05",
            "hard_shell",
            14.50,
            "1.25 lb Hard Shell Live Lobster $18.00/lb",
            85,
            "web",
            "https://pinetreeseafood.com/shop",
        ),
        (
            "Harbor Fish Market (Lobster)",
            "web-harbor-2026-07-05",
            "hard_shell",
            15.30,
            "Live Maine Hard Shell Lobster $15.30–$29.10/lb",
            90,
            "web",
            "https://harborfish.com/product-category/all/lobster/live-lobster",
        ),
        (
            "Free Range Fish & Lobster",
            "fb-freerange-2026-07-05",
            "soft_shell",
            9.99,
            "soft shell chix $9.99/lb",
            72,
            "facebook_search",
            "https://facebook.com/freerangefishandlobster/posts/1",
        ),
        (
            "SoPo Seafood Market & Raw Bar",
            "fb-sopo-2026-07-05",
            "hard_shell",
            8.95,
            "hard shell lobster $8.95/lb",
            80,
            "facebook_search",
            "https://facebook.com/soposeafood/posts/1",
        ),
    ]

    for market, post_id, key, price, snippet, conf, source, url in lobster_current:
        extra = {}
        if market == "Harbor Fish Market (Lobster)":
            extra = {"price_is_range": True, "raw_price_high": 29.1}
        rows.append(
            _row(
                market=market,
                post_id=post_id,
                kind="lobster_tier",
                key=key,
                price=price,
                unit="lb",
                snippet=snippet,
                confidence=conf,
                source=source,
                source_url=url,
                observed_at=today,
                extra=extra or None,
            )
        )

    rows.append(
        _row(
            market="Harbor Fish Market (Oysters)",
            post_id="web-harbor-oysters-2026-07-05",
            kind="oyster_tier",
            key="select",
            price=22.0,
            unit="doz",
            snippet="Select oysters $22/doz",
            confidence=88,
            source="web",
            source_url="https://harborfish.com/product-category/all/shellfish/oysters",
            observed_at=today,
        )
    )

    for market, post_id, key, price, snippet in [
        (
            "Pine Tree Seafood & Produce",
            "web-pinetree-special-2026-07-05",
            "lobster_roll",
            24.99,
            "Maine Lobster Roll $24.99",
        ),
        (
            "Harbor Fish Market (Lobster)",
            "web-harbor-special-2026-07-05",
            "chowder",
            9.99,
            "Haddock Chowder $9.99/pint",
        ),
        (
            "Ancient Mariner Lobster Co.",
            "fb-am-special-2026-07-05",
            "scallops",
            18.99,
            "Fresh scallops $18.99/lb",
        ),
    ]:
        rows.append(
            _row(
                market=market,
                post_id=post_id,
                kind="special",
                key=key,
                price=price,
                unit="ea" if key == "lobster_roll" else "lb",
                snippet=snippet,
                confidence=75,
                source="web" if market.startswith("Pine") or market.startswith("Harbor") else "facebook",
                source_url=f"https://example.com/{post_id}",
                observed_at=today,
            )
        )

    # Trend history within 7-day freshness window (6 prior days + today)
    for days_ago in range(6, 0, -1):
        dt = today - timedelta(days=days_ago)
        soft_price = round(12.0 + (days_ago % 5) * 0.25, 2)
        hard_price = round(14.0 + (days_ago % 4) * 0.35, 2)
        rows.append(
            _row(
                market="Pine Tree Seafood & Produce",
                post_id=f"trend-soft-{days_ago}",
                kind="lobster_tier",
                key="soft_shell",
                price=soft_price,
                unit="lb",
                snippet=f"soft shell lobster ${soft_price}/lb",
                confidence=80,
                source="web",
                source_url="https://pinetreeseafood.com/shop",
                observed_at=dt,
            )
        )
        rows.append(
            _row(
                market="Harbor Fish Market (Lobster)",
                post_id=f"trend-hard-{days_ago}",
                kind="lobster_tier",
                key="hard_shell",
                price=hard_price,
                unit="lb",
                snippet=f"hard shell lobster ${hard_price}/lb",
                confidence=85,
                source="web",
                source_url="https://harborfish.com/product-category/all/lobster/live-lobster",
                observed_at=dt,
            )
        )

    return rows


def build_history(prices: list[dict]) -> list[dict]:
    seen: set[str] = set()
    rows: list[dict] = []
    for p in prices:
        post_id = p["post_id"]
        if post_id in seen:
            continue
        seen.add(post_id)
        rows.append(
            {
                "market": p["market"],
                "post_id": post_id,
                "timestamp": p["observed_at"],
                "text": p["snippet"],
                "url": p["source_url"],
                "source": p["source"],
                "source_quality": 1.0 if p["source"] == "web" else 0.85,
            }
        )
    rows.append(
        {
            "market": "Five Islands Lobster Co.",
            "post_id": "ref-fiveislands-2026-07-05",
            "timestamp": _ts(BASE),
            "text": "Fresh Caught Hard Shell Lobster menu reference — no public $/lb prices",
            "url": "https://fiveislandslobster.com/menu/",
            "source": "reference",
            "source_quality": 0.7,
        }
    )
    return rows


def build_market_coverage() -> dict:
    markets = [
        {
            "market": "Ancient Mariner Lobster Co.",
            "name": "Ancient Mariner Lobster Co.",
            "posts_fetched": 1,
            "passed_rows": 1,
            "cumulative_passed_rows": 1,
            "status": "live",
            "blocker": None,
            "source_used": "facebook",
        },
        {
            "market": "Two Tides Seafood",
            "name": "Two Tides Seafood",
            "posts_fetched": 1,
            "passed_rows": 1,
            "cumulative_passed_rows": 1,
            "status": "live",
            "blocker": None,
            "source_used": "facebook",
        },
        {
            "market": "Scarborough Fish & Lobster",
            "name": "Scarborough Fish & Lobster",
            "posts_fetched": 1,
            "passed_rows": 1,
            "cumulative_passed_rows": 1,
            "status": "live",
            "blocker": None,
            "source_used": "facebook_search",
        },
        {
            "market": "Pine Tree Seafood & Produce",
            "name": "Pine Tree Seafood & Produce",
            "posts_fetched": 1,
            "passed_rows": 2,
            "cumulative_passed_rows": 2,
            "status": "live",
            "blocker": None,
            "source_used": "web",
        },
        {
            "market": "Harbor Fish Market (Lobster)",
            "name": "Harbor Fish Market (Lobster)",
            "posts_fetched": 1,
            "passed_rows": 2,
            "cumulative_passed_rows": 2,
            "status": "live",
            "blocker": None,
            "source_used": "web",
        },
        {
            "market": "Harbor Fish Market (Oysters)",
            "name": "Harbor Fish Market (Oysters)",
            "posts_fetched": 1,
            "passed_rows": 1,
            "cumulative_passed_rows": 1,
            "status": "live",
            "blocker": None,
            "source_used": "web",
        },
        {
            "market": "Free Range Fish & Lobster",
            "name": "Free Range Fish & Lobster",
            "posts_fetched": 1,
            "passed_rows": 1,
            "cumulative_passed_rows": 1,
            "status": "live",
            "blocker": None,
            "source_used": "facebook_search",
        },
        {
            "market": "SoPo Seafood Market & Raw Bar",
            "name": "SoPo Seafood Market & Raw Bar",
            "posts_fetched": 1,
            "passed_rows": 1,
            "cumulative_passed_rows": 1,
            "status": "live",
            "blocker": None,
            "source_used": "facebook_search",
        },
        {
            "market": "Five Islands Lobster Co.",
            "name": "Five Islands Lobster Co.",
            "posts_fetched": 1,
            "passed_rows": 0,
            "cumulative_passed_rows": 0,
            "status": "partial",
            "blocker": "reference_menu:no_live_prices",
            "source_used": "reference",
        },
    ]
    return {"updated_at": _ts(BASE), "markets": markets}


def build_run_log(coverage: dict) -> dict:
    return {
        "ts": _ts(BASE),
        "markets_attempted": 9,
        "markets_succeeded": 8,
        "posts_pulled": 10,
        "new_posts": 2,
        "prices_parsed": 11,
        "lobster_alerts": 0,
        "oyster_alerts": 0,
        "special_alerts": 0,
        "alerts_enabled": False,
        "alerts_suppressed": 0,
        "alerts_suppressed_opportunities": [],
        "alerts_suppressed_detail": [],
        "rows_persisted": 0,
        "rows_deduped": 11,
        "rows_gated": 11,
        "rows_quarantined": 0,
        "confidence_sum": 900,
        "confidence_count": 11,
        "avg_confidence": 81.8,
        "source_breakdown": {"web": 4, "facebook": 2, "facebook_search": 3, "reference": 1},
        "errors": [
            {
                "market": "Five Islands Lobster Co.",
                "fb_handle": "fiveislandslobsterco",
                "fetched": 1,
                "blocker": "reference_menu:no_live_prices",
                "source_used": "reference",
            }
        ],
        "market_coverage": coverage["markets"],
        "duration_seconds": 87.5,
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    prices = build_prices()
    coverage = build_market_coverage()
    run_log = build_run_log(coverage)
    history = build_history(prices)

    (OUT / "prices.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in prices) + "\n",
        encoding="utf-8",
    )
    (OUT / "history.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in history) + "\n",
        encoding="utf-8",
    )
    (OUT / "run-log.jsonl").write_text(json.dumps(run_log, ensure_ascii=False) + "\n", encoding="utf-8")
    (OUT / "market-coverage.json").write_text(
        json.dumps(coverage, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote B+ fixtures to {OUT} ({len(prices)} price rows)")


if __name__ == "__main__":
    main()
