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
    assert keys == {"halibut_fillet", "medium_haddock_fillet", "swordfish_steaks"}
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
    assert ("special", "medium_maine_haddock", 17.99, "lb") in specials
    assert ("special", "lobster_roll", 24.99, "ea") in specials
    assert ("special", "oak_smoked_arctic_char", 10.99, "lb") in specials


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
    tuna = {"catalog_title": "Fresh Bluefin Tuna (sushi-grade)", "key": "tuna"}
    assert _special_display_label(tuna, "Tuna") == "Bluefin Tuna (sushi-grade)"
    chowder = {"snippet": "Haddock Chowder $9.99/pint", "key": "chowder"}
    assert _special_display_label(chowder, "Chowder") == "Haddock Chowder"
    clams = {"snippet": "Fresh steamer clams - $8.99/lb", "key": "clams"}
    assert _special_display_label(clams, "Clams") == "Steamer clams"


def test_chowder_pint_unit_on_board():
    from board_render import build_board, price_parts

    row = {"snippet": "Haddock Chowder $9.99/pint", "unit": "lb", "price": 9.99}
    from board_render import _unit_from_snippet

    assert _unit_from_snippet(row) == "pint"
    amount, unit_label = price_parts(9.99, "pint")
    assert unit_label == "/pint"


def test_salvage_mashup_special_rows():
    from board_render import _salvage_mashup_special_rows

    sopo = {
        "kind": "special",
        "key": "haddock",
        "price": 11.99,
        "snippet": "50 /lb.\n• Gulf of Maine Haddock Fillet: $11.99 /lb.\n• Maine Crab Meat,",
    }
    lines = _salvage_mashup_special_rows(sopo)
    assert len(lines) == 1
    assert "Gulf of Maine Haddock" in lines[0]["snippet"]
    assert lines[0]["price"] == 11.99
    assert lines[0]["key"] == "haddock"

    crab_row = {
        "kind": "special",
        "key": "haddock",
        "price": 21.99,
        "unit": "ea",
        "snippet": "11.99 /lb.\n• Maine Crab Meat, 8 oz cup: $21.99 each.\n• North Carolina Swordfish:",
    }
    crab_lines = _salvage_mashup_special_rows(crab_row)
    assert len(crab_lines) == 1
    assert crab_lines[0]["key"] == "crab"
    assert crab_lines[0]["price"] == 21.99

    free_range = {
        "kind": "special",
        "key": "tuna",
        "price": 14.99,
        "snippet": "$14.99lb\n🐟Fresh Local bluefin Tuna loin $18.99lb\n🐚Fresh Scallops 23.",
    }
    fr_lines = _salvage_mashup_special_rows(free_range)
    assert len(fr_lines) == 1
    assert "bluefin Tuna" in fr_lines[0]["snippet"]
    assert fr_lines[0]["price"] == 18.99

    ancient_clams = {
        "kind": "special",
        "key": "clams",
        "price": 7.99,
        "unit": "lb",
        "snippet": "er Meat (1lb Bags):\n\n$64.99/lb\n\nClams:\n\n$7.99/lb\n\nMussels (sold in 2",
    }
    ancient_lines = _salvage_mashup_special_rows(ancient_clams)
    assert len(ancient_lines) == 1
    assert ancient_lines[0]["price"] == 7.99
    assert ancient_lines[0]["key"] == "clams"
    assert _is_clean_special_row(ancient_lines[0])

    swordfish_row = {
        "kind": "special",
        "key": "swordfish",
        "price": 14.99,
        "unit": "lb",
        "snippet": "lways fresh swordfish loin!!!\n\n⚔️🐟 only $14.99/lb \n\nThis deal is whil",
    }
    sword_lines = _salvage_mashup_special_rows(swordfish_row)
    assert len(sword_lines) == 1
    assert sword_lines[0]["price"] == 14.99
    assert sword_lines[0]["key"] == "swordfish"
    assert _is_clean_special_row(sword_lines[0])


def test_special_row_coherent_rejects_mislabeled_crab():
    from board_render import _special_row_coherent

    assert _special_row_coherent(
        {
            "kind": "special",
            "key": "haddock",
            "snippet": "Maine Crab Meat, 8 oz cup: $21.99 each.",
        }
    ) is False
    assert _special_row_coherent(
        {
            "kind": "special",
            "key": "crab",
            "snippet": "Maine Crab Meat, 8 oz cup: $21.99 each.",
        }
    ) is True


def test_per_oyster_price_parsing():
    from parse_prices import parse_post

    rows = parse_post("Oyster bar Fri-Sun afternoons. $3.00 per oyster.")
    oysters = [r for r in rows if r[0] == "oyster_tier"]
    assert len(oysters) == 1
    assert oysters[0][2] == 3.0
    assert oysters[0][3] == "ea"


def test_special_display_label_expands_slash_abbrev():
    row = {"snippet": "Lob/crab $39 lb", "key": "crab"}
    assert _special_display_label(row, "Crab") == "Lobster & Crab"


def test_is_publishable_special_label_rejects_unexpanded_slash_abbrev():
    from board_render import _is_publishable_special_label

    assert _is_publishable_special_label("Lob/crab") is False
    assert _is_publishable_special_label("Lobster & Crab") is True


def test_oyster_row_secondary_unit_aware():
    from board_render import _oyster_row_secondary

    assert _oyster_row_secondary("Oysters", "ea") == "each"
    assert _oyster_row_secondary("Oysters", "doz") == "per dozen"
    assert _oyster_row_secondary("Wellfleet Select", "doz") == "Wellfleet Select"


def test_oyster_html_label_not_per_dozen_for_each():
    from chalk_board_html import _item_label_without_market

    ea_row = {
        "label": "Oysters",
        "unit": "ea",
        "row_secondary": "each",
        "market_short": "Free Range",
    }
    doz_row = {
        "label": "Oysters",
        "unit": "doz",
        "row_secondary": "per dozen",
        "market_short": "Harbor Fish Oys",
    }
    assert _item_label_without_market(ea_row, section_key="oyster") == "each"
    assert _item_label_without_market(doz_row, section_key="oyster") == "per dozen"


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
        test_chowder_pint_unit_on_board,
        test_special_display_label_expands_slash_abbrev,
        test_is_publishable_special_label_rejects_unexpanded_slash_abbrev,
        test_oyster_row_secondary_unit_aware,
        test_oyster_html_label_not_per_dozen_for_each,
        test_salvage_mashup_special_rows,
        test_special_row_coherent_rejects_mislabeled_crab,
        test_per_oyster_price_parsing,
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
