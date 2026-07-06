"""Tests for market logo lookup and chalkboard sign integration."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from chalk_board_html import _html_market_sign, render_chalk_html
from market_logos import (
    LOGOS_DIR,
    MARKET_LOGO_SLUGS,
    all_configured_shorts,
    logo_data_uri,
    logo_path_for_short,
    shorts_missing_logo_files,
    validate_shortcut_coverage,
)
from market_names import MARKET_SHORTCUTS


def test_shortcut_coverage():
    validate_shortcut_coverage()
    assert set(MARKET_SHORTCUTS.values()) <= set(MARKET_LOGO_SLUGS.keys())


def test_logo_files_exist():
    missing = shorts_missing_logo_files()
    assert not missing, f"missing logo files for: {missing}"
    assert LOGOS_DIR.is_dir()


def test_logo_data_uri_roundtrip():
    uri = logo_data_uri("Ancient Mariner")
    assert uri is not None
    assert uri.startswith("data:image/")
    assert ";base64," in uri


def test_market_sign_with_logo():
    html = _html_market_sign("Pine Tree", section_key="lobster", tilt=-1.2)
    assert 'class="market-sign-logo"' in html
    assert "market-sign-frame" not in html
    assert "market-sign-board" not in html
    assert "market-sign--logo" in html
    assert 'alt="Pine Tree"' in html
    assert "data:image/" in html


def test_market_sign_without_logo():
    html = _html_market_sign("Unknown Market", section_key="oyster", tilt=0.0)
    assert "market-sign-logo" not in html
    assert "market-sign-frame" not in html
    assert "market-sign-board" not in html
    assert "market-sign--text" in html
    assert "market-sign-label" in html
    assert "Unknown Market" in html


def test_placeholder_logo_rejected():
    from market_logos import is_placeholder_logo, logo_path_for_short

    path = logo_path_for_short("Two Tides")
    if path is not None:
        assert not is_placeholder_logo(path)
    else:
        # Placeholder on disk should not be served.
        raw = LOGOS_DIR / "two-tides.webp"
        if raw.is_file():
            assert is_placeholder_logo(raw)


def test_render_chalk_includes_logos_for_known_markets():
    board = {
        "title": "Test Board",
        "subtitle": "Maine",
        "display_date": "Today",
        "updated_at": "2026-07-06T12:00:00Z",
        "sections": {
            "lobster": [
                {
                    "market_short": "Ancient Mariner",
                    "label": "Soft Shell",
                    "price_amount": "$12",
                    "unit_label": "/lb",
                    "tilt": -1.0,
                }
            ],
            "oyster": [],
            "special": [],
        },
        "market_coverage": [],
    }
    html = render_chalk_html(board)
    assert "market-sign-logo" in html
    assert 'alt="Ancient Mariner"' in html


def test_all_configured_shorts_have_mappings():
    assert len(all_configured_shorts()) == len(MARKET_LOGO_SLUGS)
