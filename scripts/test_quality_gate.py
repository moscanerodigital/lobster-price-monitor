"""Unit tests for quality_gate module."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from parse_prices import is_specials_post
from quality_gate import gate_rows, score_row, source_quality_score

FRESH_TS = datetime.now(timezone.utc).isoformat()
STALE_TS = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()


def test_source_quality():
    assert source_quality_score("web") == 1.0
    assert source_quality_score("facebook") == 1.0
    assert source_quality_score("facebook_search") == 0.9
    assert source_quality_score("google_cse") == 0.7
    assert source_quality_score("duckduckgo") == 0.5
    print("  ✓ source_quality scores")


def test_gate_passes_web_special():
    rows = [("special", "halibut", 18.99, "lb", "Fresh halibut $18.99/lb")]
    passed, quarantined = gate_rows(
        rows,
        source="web",
        observed_at=FRESH_TS,
        full_text="Fresh halibut $18.99/lb",
        parse_meta=[{"price_pos": 13, "bare_price": False, "structured": True}],
    )
    assert len(passed) == 1
    assert passed[0].gate_passed
    assert passed[0].confidence >= 70
    assert passed[0].gate_a_passed and passed[0].gate_b_passed and passed[0].gate_c_passed
    print("  ✓ web special passes all gates")


def test_gate_quarantines_low_quality_source():
    """DDG snippets rarely pass Gate B — effective conf = raw × 0.5."""
    rows = [("special", "halibut", 18.99, "lb", "halibut $18.99/lb")]
    passed, quarantined = gate_rows(
        rows,
        source="duckduckgo",
        observed_at=FRESH_TS,
        full_text="halibut $18.99/lb",
        parse_meta=[{"price_pos": 8, "bare_price": False}],
    )
    assert len(passed) == 0
    assert len(quarantined) == 1
    assert quarantined[0].failed_gate == "B"
    print("  ✓ low-quality source quarantined at gate B")


def test_gate_quarantines_out_of_band():
    row = ("lobster_tier", "hard_shell", 99.99, "lb", "hard shell $99.99/lb")
    gated = score_row(row, source="web", observed_at=FRESH_TS, full_text="hard shell $99.99/lb")
    assert not gated.gate_passed
    assert gated.reject_reason and "price_out_of_band" in gated.reject_reason
    print("  ✓ out-of-band price quarantined")


def test_lobster_tier_passes_at_60():
    row = ("lobster_tier", "hard_shell", 9.50, "lb", "hard shell $9.50/lb")
    gated = score_row(
        row, source="web", observed_at=FRESH_TS, full_text="hard shell $9.50/lb", structured=True
    )
    assert gated.gate_passed
    assert gated.confidence >= 60
    print("  ✓ lobster tier passes at threshold 60")


def test_gate_quarantines_implausible_fb_search_lobster():
    """FB search spam like 'Live lobsters $5/lb' must not pass without trusted source."""
    row = ("lobster_tier", "hard_shell", 5.0, "lb", "Live lobsters $5/lb")
    gated = score_row(
        row,
        source="facebook_search",
        observed_at=FRESH_TS,
        full_text="Newsflash!! Live lobsters $5/lb. Cooked lobsters $5.50",
    )
    assert not gated.gate_passed
    assert gated.failed_gate == "C"
    assert gated.reject_reason and "lobster_below_market_floor" in gated.reject_reason
    print("  ✓ implausible $5/lb FB search lobster quarantined")


def test_structured_catalog_lobster_passes_without_unit_in_title():
    row = ("lobster_tier", "1.25lb", 15.60, "lb", "Maine Lobster 1.25lb (Hard Shell)")
    gated = score_row(row, source="web", observed_at=FRESH_TS, structured=True)
    assert gated.gate_passed
    assert gated.confidence >= 60
    print("  ✓ structured catalog lobster passes without explicit /lb")


def test_is_specials_post():
    assert is_specials_post("halibut $18.99/lb") is True
    assert is_specials_post("chicks $8.75/lb") is False
    print("  ✓ is_specials_post AC4b logic")


def main() -> int:
    tests = [
        test_source_quality,
        test_gate_passes_web_special,
        test_gate_quarantines_low_quality_source,
        test_gate_quarantines_out_of_band,
        test_lobster_tier_passes_at_60,
        test_gate_quarantines_implausible_fb_search_lobster,
        test_structured_catalog_lobster_passes_without_unit_in_title,
        test_is_specials_post,
    ]
    failures = 0
    for t in tests:
        try:
            t()
        except AssertionError as e:
            print(f"  ✗ {t.__name__}: {e}")
            failures += 1
        except Exception as e:
            print(f"  ✗ {t.__name__}: {type(e).__name__}: {e}")
            failures += 1
    print()
    if failures == 0:
        print(f"All {len(tests)} quality gate tests passed.")
        return 0
    print(f"{failures} test(s) failed.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
