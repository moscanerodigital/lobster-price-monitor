"""Authenticated Facebook post fetch via curl_cffi (Chrome TLS impersonation).

facebook-scraper often returns 0 posts on modern FB HTML; this path uses the
logged-in session (cookies file or Chrome) and parses embedded JSON post text.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from secrets import load_fb_cookies
from urllib.parse import quote_plus

from parse_prices import is_specials_post

logger = logging.getLogger(__name__)

_TEXT_RE = re.compile(r'"text":"((?:\\.|[^"\\])*)"')
_LOBSTER_PRICE_HINT = re.compile(
    r"\$\s*\d+(?:\.\d+)?\s*(?:/\s*lb|/lb|\s*lb\b|lb\b)",
    re.IGNORECASE,
)
_SEAFOOD_MENU_HINT = re.compile(
    r"\b(?:halibut|haddock|salmon|scallop|oyster|shrimp|crab|chowder|bisque|"
    r"swordfish|tuna|cod|sole|mussel|clam|steamer)\b",
    re.IGNORECASE,
)

# Cross-market bleed tokens — reject posts clearly from another watchlist market.
_OTHER_MARKET_TOKENS: dict[str, tuple[str, ...]] = {
    "Ancient Mariner Lobster Co.": (
        "two tides",
        "cheapmainelobster",
        "pinetree",
        "harbor fish",
        "free range",
        "sopo",
        "five islands",
    ),
    "Two Tides Seafood": (
        "ancient mariner",
        "amlobsterco",
        "854-8444",
        "cheapmainelobster",
        "pinetree",
    ),
    "Scarborough Fish & Lobster": ("ancient mariner", "two tides", "854-8444"),
    "Free Range Fish & Lobster": ("ancient mariner", "two tides seafood"),
    "SoPo Seafood Market & Raw Bar": ("ancient mariner", "two tides seafood"),
    "Five Islands Lobster Co.": ("ancient mariner", "two tides", "portland"),
    "Pine Tree Seafood & Produce": ("ancient mariner", "two tides"),
    "Harbor Fish Market (Lobster)": ("ancient mariner", "two tides"),
    "Harbor Fish Market (Oysters)": ("ancient mariner", "two tides"),
}


@dataclass
class FetchDiagnostics:
    """Per-market FB curl fetch outcome for scrape logging."""

    texts_found: int = 0
    texts_filtered: int = 0
    http_errors: list[str] = field(default_factory=list)
    last_status: int | None = None

    def summary(self) -> str:
        if self.http_errors and not self.texts_found:
            return self.http_errors[-1]
        if self.texts_found and self.texts_filtered >= self.texts_found:
            return "filtered"
        if not self.texts_found:
            return "no_text"
        return "ok"


def _load_cookie_dict() -> dict[str, str] | None:
    return load_fb_cookies()


def _extract_post_texts(html: str) -> list[str]:
    texts: list[str] = []
    seen: set[str] = set()
    for m in _TEXT_RE.finditer(html):
        try:
            t = json.loads('"' + m.group(1) + '"')
        except json.JSONDecodeError:
            continue
        if len(t) < 25 or "$" not in t:
            continue
        if t in seen:
            continue
        seen.add(t)
        texts.append(t)
    return texts


def _page_urls(fb_handle: str) -> list[str]:
    handle = fb_handle.strip("/")
    if handle.isdigit():
        return [
            f"https://mbasic.facebook.com/profile.php?id={handle}",
            f"https://m.facebook.com/profile.php?id={handle}",
            f"https://www.facebook.com/profile.php?id={handle}",
        ]
    return [
        f"https://mbasic.facebook.com/{handle}",
        f"https://m.facebook.com/{handle}",
        f"https://www.facebook.com/{handle}",
        f"https://mbasic.facebook.com/{handle}/posts",
        f"https://m.facebook.com/{handle}/posts",
    ]


def _search_urls(market_name: str, fb_handle: str) -> list[str]:
    queries = [
        f"site:facebook.com {fb_handle} lobster price menu",
        f'"{market_name}" lobster $/lb',
        f"site:facebook.com {fb_handle} live lobster",
    ]
    return ["https://www.facebook.com/search/posts/?q=" + quote_plus(q) for q in queries]


def _is_spam_price_post(text: str) -> bool:
    lower = text.lower()
    if lower.count("newsflash") >= 2:
        return True
    if "get 'em while the gettin" in lower or "gettin's good" in lower:
        return True
    return False


def _text_matches_market(text: str, market_name: str, fb_handle: str) -> bool:
    if _is_spam_price_post(text):
        return False
    lower = text.lower()
    for token in _OTHER_MARKET_TOKENS.get(market_name, ()):
        if token in lower:
            return False
    if fb_handle.lower() in lower:
        return True
    if market_name.lower() in lower:
        return True
    if market_name == "Two Tides Seafood" and "two tides seafood" not in lower:
        return False
    first_word = market_name.split()[0].lower()
    if len(first_word) > 3 and first_word in lower:
        return True
    if _LOBSTER_PRICE_HINT.search(text) and any(
        kw in lower
        for kw in ("menu price", "updated price", "current menu", "hardshell:", "softshell:")
    ):
        return True
    return False


def _search_text_matches_market(text: str, market_name: str, fb_handle: str) -> bool:
    """Stricter filter for FB search results — must attribute to this market."""
    if _is_spam_price_post(text):
        return False
    if not _text_matches_market(text, market_name, fb_handle):
        return False
    lower = text.lower()
    if market_name.lower() in lower or fb_handle.lower() in lower:
        return True
    tokens = {
        "Ancient Mariner Lobster Co.": ("ancient mariner", "westbrook", "854-8444", "amlobsterco"),
        "Two Tides Seafood": ("two tides", "gorham", "397 gorham"),
        "Scarborough Fish & Lobster": ("scarborough fish", "cheapmainelobster", "697 us-1"),
        "Free Range Fish & Lobster": ("free range", "commercial st", "freerangefish"),
        "SoPo Seafood Market & Raw Bar": ("sopo", "south portland", "171 ocean", "soposeafood"),
        "Five Islands Lobster Co.": (
            "five islands",
            "georgetown",
            "fiveislands",
            "five islands lobster",
        ),
        "Pine Tree Seafood & Produce": ("pine tree", "pinetree"),
        "Harbor Fish Market (Lobster)": ("harbor fish", "harborfish"),
        "Harbor Fish Market (Oysters)": ("harbor fish", "harborfish"),
    }
    return any(t in lower for t in tokens.get(market_name, ()))


def _post_has_lobster_price(text: str) -> bool:
    lower = text.lower()
    if "lobster" not in lower and "lobstah" not in lower:
        return False
    return bool(_LOBSTER_PRICE_HINT.search(text))


def _post_is_seafood_menu(text: str) -> bool:
    """Menu/specials posts without explicit lobster $/lb."""
    if "$" not in text:
        return False
    if is_specials_post(text):
        return True
    lower = text.lower()
    if _SEAFOOD_MENU_HINT.search(text) and any(
        ch in text for ch in ("•", "\n", "menu", "today", "catch", "special")
    ):
        return True
    if _SEAFOOD_MENU_HINT.search(text) and lower.count("$") >= 2:
        return True
    return False


def _page_post_acceptable(text: str, market_name: str, fb_handle: str) -> bool:
    return (
        _post_has_lobster_price(text)
        or _text_matches_market(text, market_name, fb_handle)
        or _post_is_seafood_menu(text)
    )


def fetch_fb_posts(
    market_name: str,
    fb_handle: str,
    *,
    max_posts: int = 10,
    skip_search: bool = False,
    diagnostics: FetchDiagnostics | None = None,
) -> list[dict]:
    """Return normalized post dicts from FB page HTML (+ optional search fallback)."""
    diag = diagnostics or FetchDiagnostics()
    cookies = _load_cookie_dict()
    if not cookies:
        return []

    try:
        from curl_cffi import requests as cr
    except ImportError:
        return []

    session = cr.Session(impersonate="chrome120")
    observed = datetime.now(timezone.utc).isoformat()
    results: list[dict] = []
    seen_text: set[str] = set()

    def _add(text: str, url: str, source: str) -> None:
        if source == "facebook_search":
            if not _search_text_matches_market(text, market_name, fb_handle):
                diag.texts_filtered += 1
                return
        elif not _text_matches_market(text, market_name, fb_handle) and not _post_is_seafood_menu(
            text
        ):
            diag.texts_filtered += 1
            return
        key = text.strip()[:200]
        if key in seen_text:
            return
        seen_text.add(key)
        post_id = "fbcurl-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
        results.append(
            {
                "market": market_name,
                "post_id": post_id,
                "timestamp": observed,
                "text": text,
                "url": url,
                "source": source,
            }
        )

    for url in _page_urls(fb_handle)[:4]:
        if len(results) >= max_posts:
            break
        try:
            resp = session.get(url, cookies=cookies, timeout=15)
            diag.last_status = resp.status_code
            if resp.status_code != 200:
                diag.http_errors.append(f"http_{resp.status_code}")
                continue
            texts = _extract_post_texts(resp.text)
            diag.texts_found += len(texts)
            for text in texts:
                if _page_post_acceptable(text, market_name, fb_handle):
                    _add(text, url, "facebook")
                else:
                    diag.texts_filtered += 1
                if len(results) >= max_posts:
                    break
        except Exception as exc:
            diag.http_errors.append(type(exc).__name__)
            continue

    if not skip_search and len(results) < max_posts:
        for url in _search_urls(market_name, fb_handle)[:1]:
            if len(results) >= max_posts:
                break
            try:
                resp = session.get(url, cookies=cookies, timeout=15)
                diag.last_status = resp.status_code
                if resp.status_code != 200:
                    diag.http_errors.append(f"http_{resp.status_code}")
                    continue
                texts = _extract_post_texts(resp.text)
                diag.texts_found += len(texts)
                for text in texts:
                    if not (_post_has_lobster_price(text) or _post_is_seafood_menu(text)):
                        diag.texts_filtered += 1
                        continue
                    _add(text, url, "facebook_search")
                    if len(results) >= max_posts:
                        break
            except Exception as exc:
                diag.http_errors.append(type(exc).__name__)
                continue

    return results[:max_posts]
