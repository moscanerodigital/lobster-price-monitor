"""Web catalog parser — extracts product name + price from WooCommerce/Shopify HTML.

Different from FB post parser: structured HTML, so we look for product blocks
(`<li class="product">` for WooCommerce) and extract title + price pairs.
"""
from __future__ import annotations
import re
import urllib.request
from typing import List, Tuple


# WooCommerce price block — matches:
#   Pine Tree: <span class="woocommerce-Price-amount ..."><bdi><span class="currencySymbol">$</span>22.50</bdi></span>
#   Harbor Fish: <span class="woocommerce-Price-amount amount"><span class="currencySymbol">$</span>14.30</span>
# The currency can be "$" or the HTML entity "&#36;" or "&#036;"
# bdi is optional (Pine Tree wraps in <bdi>, Harbor Fish does not)
_PRICE_BLOCK_RE = re.compile(
    r'<span[^>]*class="[^"]*woocommerce-Price-amount[^"]*"[^>]*>'
    r'(?:\s*<bdi>)?\s*'
    r'<span[^>]*class="[^"]*currencySymbol[^"]*"[^>]*>(?:\$|&#0?36;)</span>\s*'
    r'([\d.,]+)\s*'
    r'(?:</bdi>)?\s*</span>',
    re.DOTALL | re.IGNORECASE,
)
# WooCommerce product title — works for both standard WooCommerce
# ("woocommerce-loop-product__title") and Divi builder ("entry-title de_title_module product_title")
_TITLE_RE = re.compile(
    r'<h2[^>]*class="[^"]*(?:woocommerce-loop-product__title|entry-title[^"]*product_title)[^"]*"[^>]*>\s*(.+?)\s*</h2>',
    re.DOTALL,
)
# Generic "from $X" sale price range
_RANGE_RE = re.compile(
    r'([\d.]+)\s*(?:–|-|to|through)\s*([\d.]+)',
)


def _strip_tags(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s).strip()


def parse_web_catalog(html: str) -> List[Tuple[str, float, str, str]]:
    """Extract (product_name, price, unit, raw_snippet) tuples from a web catalog page.

    Strategy: find all h2 product titles in document order, then for each one,
    find the next WooCommerce price span that appears AFTER it. This is order-
    preserving and works regardless of the product card wrapper class.
    """
    rows: List[Tuple[str, float, str, str]] = []
    # Find all h2 titles
    title_matches = list(_TITLE_RE.finditer(html))
    # Find all price spans
    price_matches = list(_PRICE_BLOCK_RE.finditer(html))

    for tm in title_matches:
        title = _strip_tags(tm.group(1))
        # Find the FIRST price span that appears AFTER this title
        # and BEFORE the next title (if any)
        next_title_pos = html.find("<h2", tm.end())
        if next_title_pos == -1:
            next_title_pos = len(html)
        candidate_prices = [p for p in price_matches
                           if tm.end() <= p.start() < next_title_pos]
        if not candidate_prices:
            continue
        price_str = candidate_prices[0].group(1)
        try:
            price = float(price_str)
        except ValueError:
            continue

        title_l = title.lower()
        # Skip lobster meat / cooked / picked / bisque — those are not LIVE lobster
        if any(kw in title_l for kw in ("lobster meat", "picked meat", "cooked", "bisque",
                                          "mac and cheese", "ravioli", "lobster mac")):
            continue

        lobster_tier = None
        oyster_tier = None
        if "lobster" in title_l:
            if "1.25" in title or "1 1/4" in title or "1¼" in title:
                lobster_tier = "1.25lb"
            elif "1.5" in title or "1 1/2" in title or "1½" in title:
                lobster_tier = "1.5lb"
            elif "1.75" in title or "1 3/4" in title or "1¾" in title:
                lobster_tier = "1.75lb"
            elif "1lb" in title_l or "1 lb" in title_l or "(1 lb" in title_l:
                lobster_tier = "1lb"
            elif "2 lb" in title_l or "2lb" in title_l or "jumbo" in title_l:
                lobster_tier = "2lb_plus"
            if "hard" in title_l:
                lobster_tier = lobster_tier or "hard_shell"
            elif "soft" in title_l:
                lobster_tier = lobster_tier or "soft_shell"
            elif "chick" in title_l:
                lobster_tier = "chicks"
        elif "oyster" in title_l:
            # Oysters from web catalog — use the live category unit. If the
            # title or price block contains "doz" or "dozen", use doz.
            # Otherwise treat as special (price per piece or per lb unclear).
            unit = "lb"  # default; downstream may reclassify
            # Crude check: if title contains "doz", use doz
            if "doz" in title_l or "dozen" in title_l:
                unit = "doz"
            # Find a grade
            from parse_prices import _find_oyster_grade_in_clause  # type: ignore
            grade = _find_oyster_grade_in_clause(title)
            if grade:
                oyster_tier = grade
            else:
                oyster_tier = "oyster"
            rows.append(("oyster_tier", oyster_tier, price, unit, title))
            continue

        if lobster_tier:
            rows.append(("lobster_tier", lobster_tier, price, "lb", title))
        else:
            slug = re.sub(r"[^a-z0-9]+", "_", title_l).strip("_")[:80]
            rows.append(("special", slug, price, "lb", title))
    return rows


def fetch_and_parse(url: str) -> List[Tuple[str, float, str, str]]:
    """Fetch a URL and parse its catalog. Never raises — returns [] on failure."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
        return parse_web_catalog(html)
    except Exception as e:
        print(f"  [web parse error] {url}: {type(e).__name__}: {e}", flush=True)
        return []
