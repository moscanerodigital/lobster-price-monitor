"""D-02: history fallback when fresh fetch gates zero rows."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import scrape_markets


def test_history_fallback_excludes_fetched_post_ids() -> None:
    fetched = [{"post_id": "fb-new-1", "text": "bad", "timestamp": "2026-07-06T12:00:00+00:00"}]
    hist = [
        {"post_id": "fb-new-1", "text": "bad", "timestamp": "2026-07-06T12:00:00+00:00"},
        {"post_id": "fb-old-1", "text": "good", "timestamp": "2026-07-05T12:00:00+00:00"},
    ]

    def fake_recent(_market: str, **kwargs):
        return hist

    original = scrape_markets.recent_history_posts
    scrape_markets.recent_history_posts = fake_recent
    try:
        extra = scrape_markets._history_fallback_posts("Test Market", fetched)
    finally:
        scrape_markets.recent_history_posts = original

    assert len(extra) == 1
    assert extra[0]["post_id"] == "fb-old-1"


def test_history_fallback_empty_when_no_fetched_posts() -> None:
    assert scrape_markets._history_fallback_posts("Test Market", []) == []


def main() -> int:
    tests = [
        test_history_fallback_excludes_fetched_post_ids,
        test_history_fallback_empty_when_no_fetched_posts,
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
    print("\nAll scrape history fallback tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
