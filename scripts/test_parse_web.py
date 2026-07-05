"""Unit tests for parse_web.parse_web_catalog()."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from parse_web import parse_web_catalog

# Minimal WooCommerce HTML fixtures
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

SAMPLES = [
    (
        PINE_TREE_FIXTURE,
        [
            ("lobster_tier", "1.25lb", 22.50, "lb"),
            ("special", "lobster_roll", 24.99, "ea"),
            ("special", "halibut", 18.99, "lb"),
        ],
    ),
    (
        HARBOR_FISH_OYSTER_FIXTURE,
        [
            ("oyster_tier", "select", 24.00, "doz"),
            ("oyster_tier", "xl", 32.00, "lb"),
        ],
    ),
]


def main() -> int:
    failures = 0
    for i, (html, expected) in enumerate(SAMPLES, 1):
        actual = parse_web_catalog(html)
        actual_red = [(k, key, p, u) for (k, key, p, u, _snip) in actual]
        ok = actual_red == expected
        if ok:
            print(f"  ✓ web sample {i}: {len(actual)} row(s)")
        else:
            print(f"  ✗ web sample {i}: MISMATCH")
            print(f"     expected: {expected}")
            print(f"     actual:   {actual_red}")
            failures += 1
    print()
    if failures == 0:
        print(f"All {len(SAMPLES)} web samples passed.")
        return 0
    print(f"{failures} web sample(s) failed.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
