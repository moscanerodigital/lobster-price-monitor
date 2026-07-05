"""AAA gate and board behavior tests."""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import board_render
import scrape_markets
import state
from board_render import build_board, get_board
from market_coverage import build_market_coverage
from markets import MARKETS
from parse_web import parse_web_catalog_rows
from state import append_jsonl_deduped, persist_key


PINE_TREE_FIXTURE = """
<ul class="products">
<li class="product">
<h2 class="woocommerce-loop-product__title">1.25 lb Hard Shell Live Lobster</h2>
<span class="woocommerce-Price-amount amount"><bdi><span class="woocommerce-Price-currencySymbol">$</span>22.50</bdi></span>
</li>
</ul>
"""

HARBOR_RANGE_FIXTURE = """
<ul class="products">
<li class="product">
<h2 class="woocommerce-loop-product__title">Live Maine Hard Shell Lobster</h2>
<span class="woocommerce-Price-amount amount"><span class="woocommerce-Price-currencySymbol">$</span>15.30</span>
<span class="woocommerce-Price-amount amount"><span class="woocommerce-Price-currencySymbol">$</span>29.10</span>
</li>
</ul>
"""


def test_no_demo_fallback_in_default_board(tmp_path: Path) -> None:
    prices = tmp_path / "prices.jsonl"
    prices.write_text(
        json.dumps({
            "market": "Pine Tree Seafood & Produce",
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "post_id": "web-test",
            "kind": "special",
            "key": "salmon",
            "price": 8.99,
            "unit": "lb",
            "snippet": "Salmon",
            "confidence": 75,
            "gate_passed": True,
            "source": "web",
            "source_url": "https://example.com",
            "parser_version": "test/1.0",
        }) + "\n",
        encoding="utf-8",
    )
    with patch.object(board_render, "read_jsonl", return_value=json.loads(prices.read_text().strip().split("\n")[0]) and [json.loads(line) for line in prices.read_text().strip().split("\n") if line]):
        board = get_board(demo=False)
    assert board.get("is_demo") is not True
    for items in board["sections"].values():
        for item in items:
            assert "pending" not in item.get("price_str", "").lower()


def test_demo_is_explicit_only() -> None:
    demo = get_board(demo=True)
    assert demo.get("is_demo") is True
    assert demo.get("live_market_count", 0) == 0


def test_no_alerts_suppresses_and_records() -> None:
    stats = {
        "alerts_suppressed": 0,
        "alerts_suppressed_opportunities": [],
        "alerts_suppressed_detail": [],
        "alerts_enabled": False,
        "lobster_alerts": 0,
        "rows_gated": 0,
        "rows_quarantined": 0,
        "confidence_sum": 0,
        "confidence_count": 0,
    }
    from quality_gate import gate_rows

    passed, _ = gate_rows(
        [("lobster_tier", "chicks", 5.0, "lb", "chicks $5/lb")],
        source="web",
        observed_at=datetime.now(timezone.utc).isoformat(),
        parse_meta=[{"structured": True}],
    )
    persist_seen: set[str] = set()
    with tempfile.TemporaryDirectory() as td:
        data_dir = Path(td)
        with patch.object(state, "DATA_DIR", data_dir), patch.object(
            scrape_markets, "alert_lobster_drop", return_value=True,
        ) as alert_fn:
            scrape_markets._process_gated_rows(
                passed, [], MARKETS[3], {
                    "post_id": "t1", "url": "https://x", "source": "web",
                },
                datetime.now(timezone.utc).isoformat(),
                stats,
                send_alerts=False,
                persist_seen=persist_seen,
            )
            alert_fn.assert_not_called()
            assert stats["alerts_suppressed"] >= 1
            if (data_dir / "prices.jsonl").exists():
                lines = [
                    line for line in (data_dir / "prices.jsonl").read_text().strip().split("\n")
                    if line
                ]
                assert len(lines) == 1


def test_pine_tree_normalization_metadata() -> None:
    rows = parse_web_catalog_rows(PINE_TREE_FIXTURE)
    assert len(rows) == 1
    row = rows[0]
    assert row.kind == "lobster_tier"
    assert row.key == "1.25lb_hard_shell"
    assert row.price == 18.0
    assert row.unit == "lb"
    assert row.raw_price == 22.5
    assert row.normalization_weight_lb == 1.25
    meta = row.persist_metadata()
    assert meta["raw_price"] == 22.5
    assert meta["normalization_weight"] == 1.25
    assert "per lobster" in row.snippet.lower() or "/lb" in row.snippet.lower()


def test_lobster_board_headlines_only_market_rate() -> None:
    """Board shows one consolidated row per market — lowest soft/hard $/lb."""
    board = build_board()
    lobster = board["sections"]["lobster"]
    assert len(lobster) <= 9
    prices = [item.get("sort_price", item["price"]) for item in lobster]
    assert all(p < 20 for p in prices), f"size upsell leaked onto board: {prices}"
    assert prices == sorted(prices)
    markets = {item["market_short"] for item in lobster}
    assert "Harbor Fish" in markets
    assert "Pine Tree" in markets
    for item in lobster:
        assert item.get("is_consolidated") is True
        detail = item.get("subtext") or item.get("row_secondary", "")
        assert "$" in detail
        assert "soft $" in detail or "hard $" in detail


def test_fb_markets_visible_when_only_hard_shell() -> None:
    """FB markets with hard-shell-only tiers must appear on the lobster board."""
    rows = [
        {
            "market": "Scarborough Fish & Lobster",
            "observed_at": "2026-07-05T03:09:07+00:00",
            "post_id": "fb-scar",
            "kind": "lobster_tier",
            "key": "hard_shell",
            "price": 9.99,
            "unit": "lb",
            "snippet": "Live hard shell $9.99/lb",
            "confidence": 76,
            "gate_passed": True,
            "source": "facebook_search",
            "display_price": 9.99,
            "display_unit": "lb",
        },
        {
            "market": "Pine Tree Seafood & Produce",
            "observed_at": "2026-07-05T03:09:07+00:00",
            "post_id": "web-pine",
            "kind": "lobster_tier",
            "key": "1lb_soft_shell",
            "price": 13.5,
            "unit": "lb",
            "snippet": "1 lb soft",
            "confidence": 70,
            "gate_passed": True,
            "source": "web",
            "display_price": 13.5,
            "display_unit": "lb",
        },
        {
            "market": "Pine Tree Seafood & Produce",
            "observed_at": "2026-07-05T03:09:07+00:00",
            "post_id": "web-pine",
            "kind": "lobster_tier",
            "key": "1lb_hard_shell",
            "price": 14.5,
            "unit": "lb",
            "snippet": "1 lb hard",
            "confidence": 70,
            "gate_passed": True,
            "source": "web",
            "display_price": 14.5,
            "display_unit": "lb",
        },
    ]
    with patch.object(board_render, "read_jsonl", return_value=rows):
        board = build_board()
    lobster = board["sections"]["lobster"]
    market_shorts = {item["market_short"] for item in lobster}
    assert "Scarborough F&L" in market_shorts, f"FB hard-only market missing: {market_shorts}"
    scar = next(i for i in lobster if i["market_short"] == "Scarborough F&L")
    assert "hard $9.99" in (scar.get("row_secondary") or "")


def test_harbor_fish_range_not_misleading() -> None:
    rows = parse_web_catalog_rows(HARBOR_RANGE_FIXTURE)
    assert len(rows) == 1
    row = rows[0]
    assert row.price == 15.30
    assert row.price_high == 29.10
    assert row.price_display_type == "range"
    meta = row.persist_metadata()
    assert meta.get("price_is_range") is True
    assert meta.get("raw_price_high") == 29.10
    assert "15.30" in row.snippet and "29.10" in row.snippet


def test_persist_dedupe_prevents_duplicate_rows() -> None:
    seen: set[str] = set()
    row = {
        "market": "Pine Tree Seafood & Produce",
        "post_id": "web-x",
        "kind": "special",
        "key": "salmon",
        "price": 8.99,
        "unit": "lb",
        "source": "web",
    }
    with tempfile.TemporaryDirectory() as td:
        data_dir = Path(td)
        with patch.object(state, "DATA_DIR", data_dir):
            assert append_jsonl_deduped("prices.jsonl", row, seen=seen) is True
            assert append_jsonl_deduped("prices.jsonl", row, seen=seen) is False
            lines = (data_dir / "prices.jsonl").read_text(encoding="utf-8").strip().split("\n")
            assert len(lines) == 1


def test_lobster_board_hides_size_premium_tiers() -> None:
    """Board shows chix/1 lb market rates only — not 1¼–1½ lb upsell tiers."""
    rows = [
        {
            "market": "Harbor Fish Market (Lobster)",
            "observed_at": "2026-07-05T02:31:56+00:00",
            "post_id": "web-harbor",
            "kind": "lobster_tier",
            "key": "chicks_soft_shell",
            "price": 14.3,
            "unit": "lb",
            "snippet": "chix soft",
            "confidence": 70,
            "gate_passed": True,
            "source": "web",
            "display_price": 14.3,
            "display_unit": "lb",
        },
        {
            "market": "Harbor Fish Market (Lobster)",
            "observed_at": "2026-07-05T02:31:56+00:00",
            "post_id": "web-harbor",
            "kind": "lobster_tier",
            "key": "chicks_hard_shell",
            "price": 15.3,
            "unit": "lb",
            "snippet": "chix hard",
            "confidence": 70,
            "gate_passed": True,
            "source": "web",
            "display_price": 15.3,
            "display_unit": "lb",
        },
        {
            "market": "Harbor Fish Market (Lobster)",
            "observed_at": "2026-07-05T02:31:56+00:00",
            "post_id": "web-harbor",
            "kind": "lobster_tier",
            "key": "1.25lb_soft_shell",
            "price": 20.25,
            "unit": "lb",
            "snippet": "size upsell",
            "confidence": 70,
            "gate_passed": True,
            "source": "web",
            "display_price": 20.25,
            "display_unit": "lb",
        },
        {
            "market": "Pine Tree Seafood & Produce",
            "observed_at": "2026-07-05T02:31:56+00:00",
            "post_id": "web-pine",
            "kind": "lobster_tier",
            "key": "1lb_soft_shell",
            "price": 13.5,
            "unit": "lb",
            "snippet": "1 lb soft",
            "confidence": 70,
            "gate_passed": True,
            "source": "web",
            "display_price": 13.5,
            "display_unit": "lb",
        },
        {
            "market": "Pine Tree Seafood & Produce",
            "observed_at": "2026-07-05T02:31:56+00:00",
            "post_id": "web-pine",
            "kind": "lobster_tier",
            "key": "1lb_hard_shell",
            "price": 14.5,
            "unit": "lb",
            "snippet": "1 lb hard",
            "confidence": 70,
            "gate_passed": True,
            "source": "web",
            "display_price": 14.5,
            "display_unit": "lb",
        },
        {
            "market": "Pine Tree Seafood & Produce",
            "observed_at": "2026-07-05T02:31:56+00:00",
            "post_id": "web-pine",
            "kind": "lobster_tier",
            "key": "1.5lb_soft_shell",
            "price": 15.0,
            "unit": "lb",
            "snippet": "size upsell",
            "confidence": 70,
            "gate_passed": True,
            "source": "web",
            "display_price": 15.0,
            "display_unit": "lb",
        },
    ]
    with patch.object(board_render, "read_jsonl", return_value=rows):
        board = build_board()
    lobster = board["sections"]["lobster"]
    assert len(lobster) == 2
    prices = [item["sort_price"] for item in lobster]
    assert prices == sorted(prices)
    assert all(p < 20 for p in prices)
    for item in lobster:
        assert item.get("is_consolidated") is True
        detail = item.get("subtext") or item.get("row_secondary", "")
        assert "$" in detail
        assert "soft $" in detail or "hard $" in detail
    harbor = next(i for i in lobster if "Harbor" in i["market_short"])
    assert harbor["sort_price"] == 14.3
    harbor_detail = harbor.get("subtext") or harbor.get("row_secondary", "")
    assert "soft $14.30" in harbor_detail
    assert "hard $15.30" in harbor_detail
    pine = next(i for i in lobster if i["market_short"] == "Pine Tree")
    assert pine["sort_price"] == 13.5


def test_five_islands_bogus_five_dollar_hidden() -> None:
    """Five Islands must not show a $5/lb lobster headline from FB search spam."""
    rows = [
        {
            "market": "Five Islands Lobster Co.",
            "observed_at": "2026-07-05T03:14:53+00:00",
            "post_id": "fbcurl-9a40628d7d8360f0",
            "kind": "lobster_tier",
            "key": "hard_shell",
            "price": 5.0,
            "unit": "lb",
            "snippet": "Newsflash!! Live lobsters $5/lb",
            "confidence": 68,
            "gate_passed": True,
            "source": "facebook_search",
        },
        {
            "market": "Pine Tree Seafood & Produce",
            "observed_at": "2026-07-05T03:09:07+00:00",
            "post_id": "web-pine",
            "kind": "lobster_tier",
            "key": "1lb_soft_shell",
            "price": 13.5,
            "unit": "lb",
            "snippet": "1 lb soft",
            "confidence": 70,
            "gate_passed": True,
            "source": "web",
            "display_price": 13.5,
            "display_unit": "lb",
        },
    ]
    with patch.object(board_render, "read_jsonl", return_value=rows):
        board = build_board()
    lobster = board["sections"]["lobster"]
    market_shorts = {item["market_short"] for item in lobster}
    assert "Five Islands" not in market_shorts, f"bogus Five Islands price leaked: {lobster}"
    assert "Pine Tree" in market_shorts


def test_market_coverage_all_nine_markets() -> None:
    coverage = build_market_coverage()
    assert len(coverage) == 9
    names = {c["name"] for c in coverage}
    assert names == {m["name"] for m in MARKETS}
    for entry in coverage:
        assert entry["status"] in ("live", "blocked", "partial")


def main() -> int:
    tests = [
        test_no_demo_fallback_in_default_board,
        test_demo_is_explicit_only,
        test_pine_tree_normalization_metadata,
        test_lobster_board_headlines_only_market_rate,
        test_fb_markets_visible_when_only_hard_shell,
        test_harbor_fish_range_not_misleading,
        test_lobster_board_hides_size_premium_tiers,
        test_five_islands_bogus_five_dollar_hidden,
        test_persist_dedupe_prevents_duplicate_rows,
        test_market_coverage_all_nine_markets,
        test_no_alerts_suppresses_and_records,
    ]
    failures = 0
    for t in tests:
        try:
            if t.__name__ == "test_no_demo_fallback_in_default_board":
                with tempfile.TemporaryDirectory() as td:
                    prices = Path(td) / "prices.jsonl"
                    prices.write_text(
                        json.dumps({
                            "market": "Pine Tree Seafood & Produce",
                            "observed_at": datetime.now(timezone.utc).isoformat(),
                            "post_id": "web-test",
                            "kind": "special",
                            "key": "salmon",
                            "price": 8.99,
                            "unit": "lb",
                            "snippet": "Salmon",
                            "confidence": 75,
                            "gate_passed": True,
                            "source": "web",
                            "source_url": "https://example.com",
                        }) + "\n",
                        encoding="utf-8",
                    )
                    with patch.object(state, "DATA_DIR", Path(td)), patch.object(board_render, "DATA_DIR", Path(td)):
                        board = get_board(demo=False)
                    assert board.get("is_demo") is not True
                    assert board["total_items"] >= 1
                print(f"  ✓ {t.__name__}")
                continue
            t()
            print(f"  ✓ {t.__name__}")
        except Exception as e:
            print(f"  ✗ {t.__name__}: {e}")
            failures += 1
    print()
    if failures:
        print(f"{failures} AAA test(s) failed.")
        return 1
    print(f"All {len(tests)} AAA tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
