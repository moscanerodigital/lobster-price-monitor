#!/usr/bin/env python3
"""Download and optimize market logos into assets/logos/."""

from __future__ import annotations

import argparse
import json
import re
import sys
from io import BytesIO
from pathlib import Path
from urllib.parse import urljoin, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))

from market_logos import FB_HANDLE_SLUGS, LOGO_FB_OVERRIDES, LOGOS_DIR, is_placeholder_logo
from markets import MARKETS
from secrets import load_fb_cookies

try:
    from PIL import Image
except ImportError as exc:  # pragma: no cover
    raise SystemExit("Pillow required: pip install Pillow") from exc

try:
    import requests
except ImportError as exc:  # pragma: no cover
    raise SystemExit("requests required: pip install requests") from exc

OPT_SIZE = 96
WEBP_QUALITY = 82
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _session() -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = _USER_AGENT
    return s


def _is_image(content: bytes, content_type: str = "") -> bool:
    if not content or len(content) < 100:
        return False
    if "image" in content_type.lower():
        return True
    return content[:4] in (b"\x89PNG", b"GIF8", b"\xff\xd8\xff", b"RIFF")


def _fetch_image(
    session: requests.Session,
    url: str,
    *,
    cookies: dict[str, str] | None = None,
) -> bytes | None:
    try:
        resp = session.get(url, cookies=cookies, timeout=20, allow_redirects=True)
        ct = resp.headers.get("content-type", "")
        if resp.status_code == 200 and _is_image(resp.content, ct):
            return resp.content
    except requests.RequestException:
        pass
    return None


def _icon_from_html(base_url: str, html: str) -> str | None:
    patterns = (
        r'<link[^>]+rel=["\'](?:shortcut )?icon["\'][^>]+href=["\']([^"\']+)',
        r'<link[^>]+href=["\']([^"\']+)["\'][^>]+rel=["\'](?:shortcut )?icon',
        r'<link[^>]+rel=["\'"]apple-touch-icon[^"\']*["\'][^>]+href=["\']([^"\']+)',
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image',
    )
    for pat in patterns:
        match = re.search(pat, html, re.IGNORECASE)
        if match:
            return urljoin(base_url, match.group(1))
    parsed = urlparse(base_url)
    return f"{parsed.scheme}://{parsed.netloc}/favicon.ico"


def _profile_pic_from_fb_html(html: str) -> str | None:
    patterns = (
        r'"profilePicLarge"\s*:\s*\{\s*"uri"\s*:\s*"([^"]+)"',
        r'"profile_picture"\s*:\s*\{\s*"uri"\s*:\s*"([^"]+)"',
        r'property="og:image" content="(https://[^"]+)"',
    )
    for pat in patterns:
        match = re.search(pat, html)
        if match:
            return match.group(1).replace("\\/", "/")
    return None


def _optimize_to_webp(raw: bytes, dest: Path) -> None:
    im = Image.open(BytesIO(raw))
    if im.mode not in ("RGB", "RGBA"):
        im = im.convert("RGBA")
    elif im.mode == "RGB":
        im = im.convert("RGBA")
    im.thumbnail((OPT_SIZE, OPT_SIZE), Image.Resampling.LANCZOS)
    dest.parent.mkdir(parents=True, exist_ok=True)
    im.save(dest, "WEBP", quality=WEBP_QUALITY, method=6)


def _sources_for_market(slug: str, market: dict) -> list[tuple[str, str]]:
    """Return (label, url) pairs in priority order."""
    sources: list[tuple[str, str]] = []
    for key in ("web", "reference_url"):
        url = market.get(key)
        if url:
            sources.append((key, url))
    handle = LOGO_FB_OVERRIDES.get(slug) or market.get("fb_handle")
    if handle:
        sources.append(
            ("fb_graph", f"https://graph.facebook.com/{handle}/picture?type=large")
        )
    if market.get("fb_handle"):
        sources.append(("fb_page", f"https://www.facebook.com/{market['fb_handle']}"))
    return sources


def fetch_slug(
    slug: str,
    market: dict,
    *,
    session: requests.Session,
    cookies: dict[str, str] | None,
    force: bool = False,
) -> tuple[str, str] | None:
    """Fetch one logo; returns (slug, source_label) or None."""
    dest = LOGOS_DIR / f"{slug}.webp"
    if dest.is_file() and not force:
        return slug, "cached"

    for label, url in _sources_for_market(slug, market):
        if label == "fb_graph":
            raw = _fetch_image(session, url)
            if raw:
                _optimize_to_webp(raw, dest)
                if is_placeholder_logo(dest):
                    dest.unlink(missing_ok=True)
                    continue
                return slug, label
            continue

        if label in ("web", "reference_url"):
            try:
                resp = session.get(url, timeout=20)
            except requests.RequestException:
                continue
            if resp.status_code != 200:
                continue
            icon_url = _icon_from_html(url, resp.text)
            raw = _fetch_image(session, icon_url) if icon_url else None
            if raw:
                _optimize_to_webp(raw, dest)
                if is_placeholder_logo(dest):
                    dest.unlink(missing_ok=True)
                    continue
                return slug, f"{label}:{icon_url}"
            og = re.search(
                r'property=["\']og:image["\'][^>]+content=["\']([^"\']+)',
                resp.text,
                re.IGNORECASE,
            )
            if og:
                raw = _fetch_image(session, og.group(1))
                if raw:
                    _optimize_to_webp(raw, dest)
                    if is_placeholder_logo(dest):
                        dest.unlink(missing_ok=True)
                        continue
                    return slug, f"{label}:og_image"
            continue

        if label == "fb_page" and cookies:
            try:
                resp = session.get(url, cookies=cookies, timeout=20)
            except requests.RequestException:
                continue
            pic_url = _profile_pic_from_fb_html(resp.text)
            if pic_url:
                raw = _fetch_image(session, pic_url, cookies=cookies)
                if raw:
                    _optimize_to_webp(raw, dest)
                    if is_placeholder_logo(dest):
                        dest.unlink(missing_ok=True)
                        continue
                    return slug, "fb_page_scrape"

    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch market logos into assets/logos/")
    parser.add_argument("--force", action="store_true", help="Re-download existing logos")
    args = parser.parse_args()

    session = _session()
    cookies = load_fb_cookies()
    seen_slugs: set[str] = set()
    results: list[tuple[str, str]] = []
    missing: list[str] = []

    for market in MARKETS:
        handle = market.get("fb_handle")
        if not handle:
            continue
        slug = FB_HANDLE_SLUGS.get(handle)
        if not slug or slug in seen_slugs:
            continue
        seen_slugs.add(slug)
        outcome = fetch_slug(
            slug, market, session=session, cookies=cookies, force=args.force
        )
        if outcome:
            results.append(outcome)
            print(f"OK  {outcome[0]:20} via {outcome[1]}")
        else:
            missing.append(slug)
            print(f"MISS {slug:20} ({market['name']})", file=sys.stderr)

    if missing:
        print(f"\nMissing logos for: {', '.join(missing)}", file=sys.stderr)
        return 1
    print(f"\n{len(results)} logos in {LOGOS_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
