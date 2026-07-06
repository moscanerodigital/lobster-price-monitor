"""Tests for specials parsing, gating, and board capping."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from board_render import _cap_specials_by_market, _is_clean_special_row, _special_display_label
from parse_prices import is_specials_post, parse_post
from parse_web import parse_web_catalog
from quality_gate import gate_rows

HARBOR_FISH_FIXTURE = """
<ul class="products">
<li class="product">
<h2 class="entry-title product_title">Fresh Halibut Fillet</h2>
<span class="woocommerce-Price-amount amount"><span class="woocommerce-Price-currencySymbol">$</span>29.99</span>
</li>
<li class="product">
<h2 class="entry-title product_title">Fresh Medium Haddock Fillet</h2>
<span class="woocommerce-Price-amount amount"><span class="woocommerce-Price-currencySymbol">$</span>16.99</span>
</li>
<li class="product">
<h2 class="entry-title product_title">Fresh Swordfish Steaks</h2>
<span class="woocommerce-Price-amount amount"><span class="woocommerce-Price-currencySymbol">$</span>21.99</span>
</li>
</ul>
"""

PINE_TREE_SPECIALS_FIXTURE = """
<ul class="products">
<li class="product">
<h2 class="woocommerce-loop-product__title">Fresh Medium Maine Haddock</h2>
<span class="woocommerce-Price-amount amount"><bdi><span class="woocommerce-Price-currencySymbol">$</span>17.99</bdi></span>
</li>
<li class="product">
<h2 class="woocommerce-loop-product__title">Lobster Roll</h2>
<span class="woocommerce-Price-amount amount"><bdi><span class="woocommerce-Price-currencySymbol">$</span>24.99</bdi></span>
</li>
<li class="product">
<h2 class="woocommerce-loop-product__title">Oak Smoked Arctic Char</h2>
<span class="woocommerce-Price-amount amount"><bdi><span class="woocommerce-Price-currencySymbol">$</span>10.99</bdi></span>
</li>
</ul>
"""

FB_ANCIENT_MARINER_FIXTURE = (
    "Today's catch at Ancient Mariner! Fresh halibut $18.99/lb, "
    "haddock $9.99/lb, and lobster rolls $22 each while they last."
)


def test_harbor_fish_web_specials_gate():
    rows = parse_web_catalog(HARBOR_FISH_FIXTURE)
    specials = [r for r in rows if r[0] == "special"]
    assert len(specials) == 3
    keys = {r[1] for r in specials}
    assert keys == {"halibut", "haddock", "swordfish"}
    meta = [{"structured": True} for _ in specials]
    passed, quarantined = gate_rows(
        specials,
        source="web",
        observed_at="2026-07-05T12:00:00+00:00",
        parse_meta=meta,
    )
    assert len(passed) == 3
    assert not quarantined


def test_pine_tree_web_specials():
    rows = parse_web_catalog(PINE_TREE_SPECIALS_FIXTURE)
    specials = [(k, key, price, unit) for k, key, price, unit, _ in rows if k == "special"]
    assert ("special", "haddock", 17.99, "lb") in specials
    assert ("special", "lobster_roll", 24.99, "ea") in specials
    assert ("special", "arctic_char", 10.99, "lb") in specials


def test_fb_specials_post_parsing():
    assert is_specials_post(FB_ANCIENT_MARINER_FIXTURE) is True
    parsed = parse_post(FB_ANCIENT_MARINER_FIXTURE)
    special_rows = [(k, key, price, unit) for k, key, price, unit, _ in parsed if k == "special"]
    assert ("special", "halibut", 18.99, "lb") in special_rows
    assert ("special", "haddock", 9.99, "lb") in special_rows
    assert ("special", "lobster_roll", 22.0, "ea") in special_rows


def test_is_clean_special_row_rejects_fb_mashup():
    sopo_row = {
        "kind": "special",
        "key": "haddock",
        "snippet": "50 /lb.\n• Gulf of Maine Haddock Fillet: $11.99 /lb.\n• Maine Crab Meat,",
    }
    assert _is_clean_special_row(sopo_row) is False


def test_is_clean_special_row_accepts_catalog_and_web_snippets():
    assert _is_clean_special_row(
        {"catalog_title": "Fresh Medium Haddock Fillet", "snippet": "ignored"}
    )
    assert _is_clean_special_row(
        {"snippet": "Fresh halibut $18.99/lb", "key": "halibut"}
    )
    assert _is_clean_special_row({"snippet": "Lobster Roll", "key": "lobster_roll"})


def test_special_display_label_strips_price_and_fresh_prefix():
    row = {"snippet": "Fresh halibut $18.99/lb", "key": "halibut"}
    assert _special_display_label(row, "Halibut") == "halibut"
    catalog = {"catalog_title": "Fresh Medium Haddock Fillet", "key": "haddock"}
    assert _special_display_label(catalog, "Haddock") == "Medium Haddock Fillet"


def test_cap_specials_preserves_all_markets():
    items = []
    for i, market in enumerate(("Market A", "Market B", "Market C", "Market D", "Market E")):
        for j in range(4):
            items.append(
                {
                    "market": market,
                    "market_short": market,
                    "label": f"Item {j}",
                    "price": 10 + j,
                    "sort_price": 10 + j,
                    "confidence": 80 - j,
                }
            )
    capped = _cap_specials_by_market(items)
    markets_shown = {item["market"] for item in capped}
    assert markets_shown == {"Market A", "Market B", "Market C", "Market D", "Market E"}
    # 5 markets × 4 per market fits under _MAX_SPECIALS_TOTAL (24)
    assert len(capped) == 20


def main() -> int:
    tests = [
        test_harbor_fish_web_specials_gate,
        test_pine_tree_web_specials,
        test_fb_specials_post_parsing,
        test_is_clean_special_row_rejects_fb_mashup,
        test_is_clean_special_row_accepts_catalog_and_web_snippets,
        test_special_display_label_strips_price_and_fresh_prefix,
        test_cap_specials_preserves_all_markets,
    ]
    failures = 0
    for test in tests:
        try:
            test()
            print(f"  ✓ {test.__name__}")
        except Exception as e:
            print(f"  ✗ {test.__name__}: {e}")
            failures += 1
    print()
    if failures == 0:
        print(f"All {len(tests)} specials tests passed.")
        return 0
    print(f"{failures} test(s) failed.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
