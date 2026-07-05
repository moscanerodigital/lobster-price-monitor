"""Unit tests for parse_web catalog parsing."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from parse_web import parse_web_catalog, parse_web_catalog_rows

PINE_TREE_FIXTURE = """
<ul class="products">
<li class="product">
<h2 class="woocommerce-loop-product__title">1.25 lb Hard Shell Live Lobster</h2>
<span class="woocommerce-Price-amount amount"><bdi><span class="woocommerce-Price-currencySymbol">$</span>22.50</bdi></span>
</li>
<li class="product">
<h2 class="woocommerce-loop-product__title">Lobster Roll</h2>
<span class="woocommerce-Price-amount amount"><bdi><span class="woocommerce-Price-currencySymbol">$</span>24.99</bdi></span>
</li>
<li class="product">
<h2 class="woocommerce-loop-product__title">Fresh Halibut per lb</h2>
<span class="woocommerce-Price-amount amount"><bdi><span class="woocommerce-Price-currencySymbol">$</span>18.99</bdi></span>
</li>
<li class="product">
<h2 class="woocommerce-loop-product__title">Picked Lobster Meat</h2>
<span class="woocommerce-Price-amount amount"><bdi><span class="woocommerce-Price-currencySymbol">$</span>69.99</bdi></span>
</li>
</ul>
"""

HARBOR_FISH_OYSTER_FIXTURE = """
<ul class="products">
<li class="product">
<h2 class="entry-title de_title_module product_title">Wellfleet Select Oysters per dozen</h2>
<span class="woocommerce-Price-amount amount"><span class="woocommerce-Price-currencySymbol">$</span>24.00</span>
</li>
<li class="product">
<h2 class="entry-title de_title_module product_title">XL Kumamoto Oysters</h2>
<span class="woocommerce-Price-amount amount"><span class="woocommerce-Price-currencySymbol">$</span>32.00</span>
</li>
</ul>
"""

HARBOR_FISH_LOBSTER_RANGE_FIXTURE = """
<ul class="products">
<li class="product">
<h2 class="entry-title product_title">Live Maine Hard Shell Lobster</h2>
<span class="woocommerce-Price-amount amount"><span class="woocommerce-Price-currencySymbol">$</span>15.30</span>
<span class="woocommerce-Price-amount amount"><span class="woocommerce-Price-currencySymbol">$</span>29.10</span>
</li>
</ul>
"""

HARBOR_FISH_LOBSTER_VARIATION_FIXTURE = """
<h2 class="entry-title de_title_module product_title">Live Maine Hard Shell Lobster</h2>
<span class="price"><span class="woocommerce-Price-amount amount"><span class="woocommerce-Price-currencySymbol">&#036;</span>15.30</span> <span>&ndash;</span> <span class="woocommerce-Price-amount amount"><span class="woocommerce-Price-currencySymbol">&#036;</span>29.10</span></span>
<form data-product_variations="[{&quot;attributes&quot;:{&quot;attribute_pa_size&quot;:&quot;chix&quot;},&quot;display_price&quot;:15.3},{&quot;attributes&quot;:{&quot;attribute_pa_size&quot;:&quot;1-14-lb&quot;},&quot;display_price&quot;:21.25},{&quot;attributes&quot;:{&quot;attribute_pa_size&quot;:&quot;1-12-lb&quot;},&quot;display_price&quot;:29.1}]">
"""

SAMPLES = [
    (
        PINE_TREE_FIXTURE,
        [
            ("lobster_tier", "1.25lb_hard_shell", 18.00, "lb"),
            ("special", "lobster_roll", 24.99, "ea"),
            ("special", "halibut", 18.99, "lb"),
        ],
    ),
    (
        HARBOR_FISH_OYSTER_FIXTURE,
        [
            ("oyster_tier", "select", 24.00, "doz"),
            ("oyster_tier", "xl", 32.00, "doz"),
        ],
    ),
    (
        HARBOR_FISH_LOBSTER_RANGE_FIXTURE,
        [
            ("lobster_tier", "hard_shell", 15.30, "lb"),
        ],
    ),
]


def test_harbor_range_metadata() -> None:
    rows = parse_web_catalog_rows(HARBOR_FISH_LOBSTER_RANGE_FIXTURE)
    assert len(rows) == 1
    row = rows[0]
    assert row.price_high == 29.10
    assert row.price_display_type == "range"
    assert "29.10" in row.snippet


def test_harbor_fish_variation_rows() -> None:
    rows = parse_web_catalog_rows(HARBOR_FISH_LOBSTER_VARIATION_FIXTURE)
    assert len(rows) == 3
    prices = sorted(r.price for r in rows)
    assert prices == [15.3, 21.25, 29.1]
    keys = {r.key for r in rows}
    assert keys == {"chicks_hard_shell", "1.25lb_hard_shell", "1.5lb_hard_shell"}
    assert all(r.price_display_type == "size_specific" for r in rows)


def test_pine_tree_raw_price_metadata() -> None:
    rows = parse_web_catalog_rows(PINE_TREE_FIXTURE)
    lobster = [r for r in rows if r.kind == "lobster_tier"][0]
    assert lobster.raw_price == 22.5
    assert lobster.price == 18.0
    assert lobster.unit == "lb"
    assert lobster.display_price == 18.0
    assert lobster.display_unit == "lb"
    assert lobster.normalized_price == 18.0
    assert lobster.normalization_weight_lb == 1.25


def main() -> int:
    failures = 0
    for t in (
        test_harbor_range_metadata,
        test_harbor_fish_variation_rows,
        test_pine_tree_raw_price_metadata,
    ):
        try:
            t()
            print(f"  ✓ {t.__name__}")
        except Exception as e:
            print(f"  ✗ {t.__name__}: {e}")
            failures += 1

    for i, (html, expected) in enumerate(SAMPLES, 1):
        actual = parse_web_catalog(html)
        actual_red = [(k, key, p, u) for (k, key, p, u, _snip) in actual]
        ok = actual_red == expected
        if ok and i == 3:
            row = parse_web_catalog_rows(html)[0]
            ok = row.price_display_type == "range" and row.price_high == 29.1
        if ok:
            print(f"  ✓ web sample {i}: {len(actual)} row(s)")
        else:
            print(f"  ✗ web sample {i}: MISMATCH")
            print(f"     expected: {expected}")
            print(f"     actual:   {actual_red}")
            failures += 1

    print()
    if failures == 0:
        print("All web samples passed.")
        return 0
    print(f"{failures} web sample(s) failed.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
