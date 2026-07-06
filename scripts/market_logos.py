"""Market logo lookup for chalkboard market signs."""

from __future__ import annotations

import base64
import mimetypes
from functools import lru_cache
from pathlib import Path

from market_names import MARKET_SHORTCUTS

LOGOS_DIR = Path(__file__).resolve().parent.parent / "assets" / "logos"

# market_short (board display name) -> logo file stem in assets/logos/
MARKET_LOGO_SLUGS: dict[str, str] = {
    "Ancient Mariner": "amlobsterco",
    "Two Tides": "two-tides",
    "Scarborough F&L": "cheapmainelobster",
    "Pine Tree": "pinetree",
    "Harbor Fish": "harborfish",
    "Harbor Fish Oys": "harborfish",
    "Free Range": "freerangefish",
    "SoPo Seafood": "soposeafood",
    "Five Islands": "fiveislands",
}

# fb_handle -> logo file stem (used by fetch_market_logos.py)
FB_HANDLE_SLUGS: dict[str, str] = {
    "amlobsterco": "amlobsterco",
    "100054888565201": "two-tides",
    "CheapMaineLobster": "cheapmainelobster",
    "PineTreeSeafood": "pinetree",
    "harborfishmarket": "harborfish",
    "freerangefishandlobster": "freerangefish",
    "soposeafood": "soposeafood",
    "fiveislandslobsterco": "fiveislands",
}

_IMAGE_EXTS = (".webp", ".png", ".jpg", ".jpeg")


def logo_path_for_short(market_short: str) -> Path | None:
    """Return on-disk logo path for a board market_short, or None."""
    slug = MARKET_LOGO_SLUGS.get(market_short)
    if not slug:
        return None
    for ext in _IMAGE_EXTS:
        path = LOGOS_DIR / f"{slug}{ext}"
        if path.is_file() and path.stat().st_size > 0:
            return path
    return None


@lru_cache(maxsize=32)
def logo_data_uri(market_short: str) -> str | None:
    """Base64 data URI for embedding in self-contained board.html."""
    path = logo_path_for_short(market_short)
    if path is None:
        return None
    mime = mimetypes.guess_type(path.name)[0] or "image/webp"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def all_configured_shorts() -> tuple[str, ...]:
    """Every market_short that has a logo slug mapping."""
    return tuple(MARKET_LOGO_SLUGS.keys())


def shorts_missing_logo_files() -> list[str]:
    """Configured market_short values with no logo file on disk."""
    return [s for s in MARKET_LOGO_SLUGS if logo_path_for_short(s) is None]


def validate_shortcut_coverage() -> None:
    """Ensure every MARKET_SHORTCUTS value has a logo slug (raises AssertionError)."""
    for short in MARKET_SHORTCUTS.values():
        assert short in MARKET_LOGO_SLUGS, f"missing logo slug for {short!r}"
