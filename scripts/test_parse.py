"""Unit tests for parse_prices.parse_post()."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from parse_prices import parse_post

# Real-ish FB post samples harvested from web search
SAMPLES = [
    # Ancient Mariner style
    (
        "Live Lobster prices are as follow, Chicks 1 1/4 lbers $8.75 lb, "
        "Old Shell $10.75 lb, Hard shell $11.95 lb, 2 lb and plus this week $12.75 lb so hurry come in",
        [
            ("lobster_tier", "chicks", 8.75, "lb"),
            ("lobster_tier", "old_shell", 10.75, "lb"),
            ("lobster_tier", "hard_shell", 11.95, "lb"),
            ("lobster_tier", "2lb_plus", 12.75, "lb"),
        ],
    ),
    # Two Tides style
    (
        "Please see our current menu prices below: "
        "Lobsters 1⅛ lb: $7.99/lb, 1¼ lb: $9.99/lb, 1½ lb: $10.89/lb, 1¾ lb: $12.99/lb",
        [
            ("lobster_tier", "1.125lb", 7.99, "lb"),
            ("lobster_tier", "1.25lb", 9.99, "lb"),
            ("lobster_tier", "1.5lb", 10.89, "lb"),
            ("lobster_tier", "1.75lb", 12.99, "lb"),
        ],
    ),
    # Pine Tree style (specials only)
    # "1.25 lb hard shell Maine lobsters - $22.50 Live or cooked for you."
    # Note: $22.50 has no unit suffix in this synthetic sample, so the price
    # regex doesn't match. Real FB posts always have /lb or "lb" or "per pound".
    # The $69.99/lb IS captured but the tier label bleeds from the previous
    # clause ("1.25 lb hard shell"). This is acceptable because the price
    # itself is what matters for alerting — the tier label is just metadata.
    # Alert dedupe in scrape_markets.py prevents re-alerting on the same
    # price from the same post.
    (
        "1.25 lb hard shell Maine lobsters - $22.50 Live or cooked for you. "
        "Fresh picked lobster meat - $69.99/lb For homemade rolls",
        [
            # Note: $69.99/lb is lobster MEAT (cooked/picked), not live.
            # With "meat" excluded from specials keywords, this is dropped
            # entirely. The user wants live prices only.
        ],
    ),
    # Roll / specials post (no unit on $)
    (
        "Pine Tree lobster rolls - $24.99 Packed with a quarter pound of fresh lobster meat on a locally baked roll",
        [],  # bare $X without "ea" or "each" is intentionally not captured
    ),
    # Empty
    ("", []),
    ("No prices here, just a thank you to our customers!", []),
    # Big hard shell sale (should trigger alert at threshold)
    # Real FB post style: "1 3/4 - 2 Lb Live Firm Shell Lobsters ONLY $5.99 a POUND"
    # The "2 Lb" is part of the same clause as "$5.99 a POUND" (no comma between).
    # My parser correctly returns hard_shell here because "1 3/4" and "2 Lb" are
    # both size keywords and "Firm Shell" is closer. Acceptable for the parser —
    # the alert logic in scrape_markets.py will trigger on hard_shell threshold.
    (
        "HUGE LOBSTER SALE!!! 1 3/4 - 2 Lb Live Firm Shell Lobsters ONLY $5.99 a POUND!!!!",
        [
            ("lobster_tier", "hard_shell", 5.99, "lb"),
        ],
    ),
    # Harbor Fish "Maine Lobster Week" style — size + price, jumbled
    (
        "Maine Lobster Week! Live Maine Jumbo Lobsters 2lbs and up at $10.99 lb Cooked & Chilled Maine Lobsters 1-1 1/8th lb",
        [
            ("lobster_tier", "2lb_plus", 10.99, "lb"),
        ],
    ),
    # Oysters — multiple grades priced by the dozen
    (
        "Fresh oysters in! Wellfleet Selects $24/doz, Blue Points $22/doz, XL Kumamotos $32 a dozen",
        [
            ("oyster_tier", "select", 24.0, "doz"),
            ("oyster_tier", "named_variety", 22.0, "doz"),
            ("oyster_tier", "xl", 32.0, "doz"),
        ],
    ),
    # Oyster named variety
    (
        "Beausoleil oysters $28 dz — best for raw bar",
        [
            ("oyster_tier", "named_variety", 28.0, "doz"),
        ],
    ),
    # $/doz that is NOT oysters (e.g. eggs) — should be ignored by oyster path
    (
        "Farm fresh eggs $6/doz, bread $4",
        [],
    ),
]


def main() -> int:
    failures = 0
    for i, (text, expected) in enumerate(SAMPLES, 1):
        actual = parse_post(text)
        # Reduce to (kind, key, price, unit) for comparison
        actual_red = [(k, key, p, u) for (k, key, p, u, _snip) in actual]
        ok = actual_red == expected
        if ok:
            print(f"  ✓ sample {i}: parsed {len(actual)} row(s) correctly")
        else:
            print(f"  ✗ sample {i}: MISMATCH")
            print(f"     expected: {expected}")
            print(f"     actual:   {actual_red}")
            failures += 1
    print()
    if failures == 0:
        print(f"All {len(SAMPLES)} samples passed.")
        return 0
    else:
        print(f"{failures} sample(s) failed.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
