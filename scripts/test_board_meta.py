"""Tests for board_meta and font_embed."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from board_meta import board_auto_refresh_seconds, cache_bust_token, generator_comment
from font_embed import caveat_font_face_css


def test_generator_comment_format() -> None:
    comment = generator_comment(gated_row_count=51, generated_at="2026-07-07T20:03:00Z", live_markets=8)
    assert "lobster-price-monitor" in comment
    assert "51 gated rows" in comment
    assert "8 live markets" in comment


def test_cache_bust_token() -> None:
    assert cache_bust_token("2026-07-07T20:03:00Z") == "20260707-2003"


def test_board_auto_refresh_disabled() -> None:
    old = os.environ.get("BOARD_AUTO_REFRESH")
    os.environ["BOARD_AUTO_REFRESH"] = "0"
    try:
        assert board_auto_refresh_seconds() is None
    finally:
        if old is None:
            os.environ.pop("BOARD_AUTO_REFRESH", None)
        else:
            os.environ["BOARD_AUTO_REFRESH"] = old


def test_caveat_font_embedded() -> None:
    css = caveat_font_face_css()
    assert "@font-face" in css or "system cursive" in css
    assert "fonts.googleapis.com" not in css


def main() -> int:
    tests = [
        test_generator_comment_format,
        test_cache_bust_token,
        test_board_auto_refresh_disabled,
        test_caveat_font_embedded,
    ]
    failed = 0
    for test in tests:
        try:
            test()
            print(f"  ✓ {test.__name__}")
        except Exception as e:
            print(f"  ✗ {test.__name__}: {e}")
            failed += 1
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
