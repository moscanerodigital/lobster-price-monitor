"""Unit tests for parse_prices.parse_post() and is_specials_post()."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from parse_prices import is_specials_post, parse_post

SAMPLES = [
    (
        "Live Lobster prices are as follow, Chicks 1 1/4 lbers $8.75 lb, "
        "Old Shell $10.75 lb, Hard shell $11.95 lb, 2 lb and plus this week $12.75 lb so hurry come in",
        [
            ("lobster_tier", "chicks", 8.75, "lb"),
            ("lobster_tier", "old_shell", 10.75, "lb"),
            ("lobster_tier", "hard_shell", 11.95, "lb"),
            ("lobster_tier", "2lb_plus_hard_shell", 12.75, "lb"),
        ],
    ),
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
    (
        "1.25 lb hard shell Maine lobsters - $22.50 Live or cooked for you. "
        "Fresh picked lobster meat - $69.99/lb For homemade rolls",
        [
            ("lobster_tier", "hard_shell", 22.50, "lb"),
        ],
    ),
    (
        "Pine Tree lobster rolls - $24.99 Packed with a quarter pound of fresh lobster meat on a locally baked roll",
        [
            ("special", "lobster_roll", 24.99, "ea"),
        ],
    ),
    ("", []),
    ("No prices here, just a thank you to our customers!", []),
    (
        "HUGE LOBSTER SALE!!! 1 3/4 - 2 Lb Live Firm Shell Lobsters ONLY $5.99 a POUND!!!!",
        [
            ("lobster_tier", "hard_shell", 5.99, "lb"),
        ],
    ),
    (
        "Maine Lobster Week! Live Maine Jumbo Lobsters 2lbs and up at $10.99 lb Cooked & Chilled Maine Lobsters 1-1 1/8th lb",
        [
            ("lobster_tier", "2lb_plus", 10.99, "lb"),
        ],
    ),
    (
        "Fresh oysters in! Wellfleet Selects $24/doz, Blue Points $22/doz, XL Kumamotos $32 a dozen",
        [
            ("oyster_tier", "select", 24.0, "doz"),
            ("oyster_tier", "named_variety", 22.0, "doz"),
            ("oyster_tier", "xl", 32.0, "doz"),
        ],
    ),
    (
        "Beausoleil oysters $28 dz — best for raw bar",
        [
            ("oyster_tier", "named_variety", 28.0, "doz"),
        ],
    ),
    (
        "Farm fresh eggs $6/doz, bread $4",
        [],
    ),
    # Scarborough mixed lobster + halibut
    (
        "Today's specials! Live hard shell $11.95/lb and fresh halibut $18.99/lb while supplies last",
        [
            ("lobster_tier", "hard_shell", 11.95, "lb"),
            ("special", "halibut", 18.99, "lb"),
        ],
    ),
    # DDG-truncated snippet style
    (
        "Scarborough Fish & Lobster - Fresh scallops $22.99/lb and clams $8.50/lb ...",
        [
            ("special", "scallops", 22.99, "lb"),
            ("special", "clams", 8.50, "lb"),
        ],
    ),
    # Chowder special
    (
        "New England clam chowder $7.99 each, come try a bowl today!",
        [
            ("special", "chowder", 7.99, "ea"),
        ],
    ),
    # Shrimp special bare price
    (
        "Gulf shrimp special - $12.99 while they last",
        [
            ("special", "shrimp", 12.99, "ea"),
        ],
    ),
    # Haddock per lb
    (
        "Fresh haddock fillets $9.99/lb, perfect for fish tacos",
        [
            ("special", "haddock", 9.99, "lb"),
        ],
    ),
    # Ancient Mariner multi-line size menu (newline-delimited tiers)
    (
        "Hardshell:\n\n"
        "1-1 1/8 lbs: $10.99/lb\n"
        "1 1/4 lbs: $11.99/lb\n"
        "1 1/2 lbs: $12.99/lb\n"
        "2+ lbs: $15.99/lb\n\n"
        "Softshell:\n\n"
        "All sizes (1lb - 1 1/2 lbs): $10.49/lb\n"
        "2+ lbs: $13.99/lb\n\n"
        "Culls (One Claw or No Claws):\n\n"
        "$8.99/lb",
        [
            ("lobster_tier", "1.125lb_hard_shell", 10.99, "lb"),
            ("lobster_tier", "1.25lb_hard_shell", 11.99, "lb"),
            ("lobster_tier", "1.5lb_hard_shell", 12.99, "lb"),
            ("lobster_tier", "2lb_plus_hard_shell", 15.99, "lb"),
            ("lobster_tier", "1.5lb_soft_shell", 10.49, "lb"),
            ("lobster_tier", "2lb_plus_soft_shell", 13.99, "lb"),
        ],
    ),
    # Salmon roll explicit
    (
        "Smoked salmon roll $14.99/roll at the counter",
        [
            ("special", "salmon", 14.99, "ea"),
        ],
    ),
]

IS_SPECIALS_POST_SAMPLES = [
    ("Fresh halibut $18.99/lb today only", True),
    ("Pine Tree lobster rolls - $24.99", True),
    ("Live hard shell $11.95/lb, chicks $8.75/lb", False),
    ("Chicks 1 1/4 lbers $8.75 lb, Old Shell $10.75 lb", False),
    ("Thank you to our customers!", False),
    ("Today's chowder special $7.99", True),
    ("Scallops and clams on special $22.99", True),
    ("HUGE LOBSTER SALE $5.99 a POUND", False),
]


def main() -> int:
    failures = 0
    for i, (text, expected) in enumerate(SAMPLES, 1):
        actual = parse_post(text)
        actual_red = [(k, key, p, u) for (k, key, p, u, _snip) in actual]
        ok = actual_red == expected
        if ok:
            print(f"  ✓ parse sample {i}: {len(actual)} row(s)")
        else:
            print(f"  ✗ parse sample {i}: MISMATCH")
            print(f"     expected: {expected}")
            print(f"     actual:   {actual_red}")
            failures += 1

    for i, (text, expected) in enumerate(IS_SPECIALS_POST_SAMPLES, 1):
        actual = is_specials_post(text)
        if actual == expected:
            print(f"  ✓ is_specials_post sample {i}")
        else:
            print(f"  ✗ is_specials_post sample {i}: expected {expected}, got {actual}")
            failures += 1

    print()
    total = len(SAMPLES) + len(IS_SPECIALS_POST_SAMPLES)
    if failures == 0:
        print(f"All {total} samples passed.")
        return 0
    print(f"{failures} sample(s) failed.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
