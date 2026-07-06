"""B-04: lobster headline shell inference and cull/snippet filtering."""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from board_lobster import (
    _collapse_lobster_headlines,
    _is_valid_headline_tier,
    _shell_from_key,
)
from board_render import build_board


def test_shell_from_key_bare_size_without_snippet_returns_none() -> None:
    assert _shell_from_key("1.125lb", "") is None
    assert _shell_from_key("chicks", "") is None


def test_shell_from_key_infers_from_snippet() -> None:
    assert _shell_from_key("1.125lb", "1 1/8 lb hard shell lobster") == "hard"
    assert _shell_from_key("1.125lb", "soft shell chix") == "soft"
    assert _shell_from_key("1.5lb_soft_shell", "") == "soft"


def test_valid_headline_tier_rejects_cull_without_tier_signal() -> None:
    item = {
        "key": "1lb_hard_shell",
        "price": 12.99,
        "snippet": "culls only — not for retail",
    }
    assert _is_valid_headline_tier(item) is False


def test_valid_headline_tier_allows_cull_when_tier_signal_present() -> None:
    item = {
        "key": "1lb_hard_shell",
        "price": 12.99,
        "snippet": "1 lb hard shell culls $12.99/lb",
    }
    assert _is_valid_headline_tier(item) is True


def test_collapse_skips_unproven_shell_rows() -> None:
    items = [
        {
            "market": "Test Market",
            "market_short": "Test",
            "key": "1.125lb",
            "price": 7.99,
            "sort_price": 7.99,
            "snippet": "lobster special",
            "observed_at": "2026-07-06T12:00:00+00:00",
            "source": "facebook",
        }
    ]
    assert _collapse_lobster_headlines(items) == []


def test_live_board_ancient_mariner_shows_soft_and_hard() -> None:
    if not os.environ.get("BOARD_QA_LIVE"):
        return
    board = build_board()
    ancient = [
        r
        for r in board["sections"]["lobster"]
        if "Ancient" in (r.get("market") or r.get("row_primary") or "")
    ]
    assert ancient, "Ancient Mariner lobster headline missing"
    detail = ancient[0].get("row_secondary", "")
    assert "soft" in detail.lower()
    assert "hard" in detail.lower()


def test_live_board_no_forced_hard_without_evidence() -> None:
    if not os.environ.get("BOARD_QA_LIVE"):
        return
    board = build_board()
    for row in board["sections"]["lobster"]:
        secondary = str(row.get("row_secondary", "")).lower()
        if "hard" in secondary and "soft" not in secondary:
            key = str(row.get("key", ""))
            snippet = str(row.get("snippet", "")).lower()
            if key in ("1.125lb", "chicks", "1lb") and "hard shell" not in snippet:
                raise AssertionError(
                    f"forced hard label without snippet evidence: {row.get('market_short')} {secondary}"
                )


def test_collapse_drops_stale_bare_shell_when_qualified_tiers_exist() -> None:
    from board_lobster import _is_stale_lobster_key

    keys = {"hard_shell", "1.125lb_hard_shell", "1.5lb_soft_shell"}
    assert _is_stale_lobster_key("hard_shell", "Ancient Mariner Lobster Co.", keys) is True
    assert _is_stale_lobster_key("1.125lb_hard_shell", "Ancient Mariner Lobster Co.", keys) is False


def test_collapse_ancient_mariner_prefers_entry_tier_over_stub() -> None:
    items = [
        {
            "market": "Ancient Mariner Lobster Co.",
            "market_short": "Ancient Mariner",
            "key": "hard_shell",
            "price": 15.99,
            "sort_price": 15.99,
            "snippet": "hard shell live lobster $15.99/lb",
            "observed_at": "2026-07-05T12:00:00+00:00",
            "source": "facebook",
        },
        {
            "market": "Ancient Mariner Lobster Co.",
            "market_short": "Ancient Mariner",
            "key": "1.125lb_hard_shell",
            "price": 10.99,
            "sort_price": 10.99,
            "snippet": "1-1 1/8 lbs: $10.99/lb",
            "observed_at": "2026-07-06T12:00:00+00:00",
            "source": "facebook",
        },
        {
            "market": "Ancient Mariner Lobster Co.",
            "market_short": "Ancient Mariner",
            "key": "1.5lb_soft_shell",
            "price": 10.49,
            "sort_price": 10.49,
            "snippet": "softshell all sizes $10.49/lb",
            "observed_at": "2026-07-06T12:00:00+00:00",
            "source": "facebook",
        },
    ]
    headlines = _collapse_lobster_headlines(items)
    assert len(headlines) == 1
    assert headlines[0]["row_secondary"] == "soft $10.49 · hard $10.99"


def main() -> int:
    tests = [
        test_shell_from_key_bare_size_without_snippet_returns_none,
        test_shell_from_key_infers_from_snippet,
        test_valid_headline_tier_rejects_cull_without_tier_signal,
        test_valid_headline_tier_allows_cull_when_tier_signal_present,
        test_collapse_skips_unproven_shell_rows,
        test_collapse_drops_stale_bare_shell_when_qualified_tiers_exist,
        test_collapse_ancient_mariner_prefers_entry_tier_over_stub,
        test_live_board_ancient_mariner_shows_soft_and_hard,
        test_live_board_no_forced_hard_without_evidence,
    ]
    failed = 0
    for test in tests:
        name = test.__name__
        try:
            test()
            print(f"  ✓ {name}")
        except Exception as e:
            print(f"  ✗ {name}: {e}")
            failed += 1
    if failed:
        print(f"\n{failed} test(s) failed")
        return 1
    print("\nAll board lobster tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
