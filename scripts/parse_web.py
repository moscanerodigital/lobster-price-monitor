"""Web catalog parser — extracts product name + price from WooCommerce HTML."""
from __future__ import annotations
import re
import urllib.request
from typing import List, Literal, Tuple

_PRICE_BLOCK_RE = re.compile(
    r'<span[^>]*class="[^"]*woocommerce-Price-amount[^"]*"[^>]*>'
    r'(?:\s*<bdi>)?\s*'
    r'<span[^>]*class="[^"]*currencySymbol[^"]*"[^>]*>(?:\$|&#0?36;)</span>\s*'
    r'([\d.,]+)\s*'
    r'(?:</bdi>)?\s*</span>',
    re.DOTALL | re.IGNORECASE,
)
_TITLE_RE = re.compile(
    r'<h2[^>]*class="[^"]*(?:woocommerce-loop-product__title|entry-title[^"]*product_title)[^"]*"[^>]*>\s*(.+?)\s*</h2>',
    re.DOTALL,
)

ParsedWebRow = Tuple[
    Literal["lobster_tier", "oyster_tier", "special"],
    str,
    float,
    str,
    str,
]


def _strip_tags(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s).strip()


def _detect_unit(title: str) -> str:
    t = title.lower()
    if any(x in t for x in ("doz", "dozen", "/dz")):
        return "doz"
    if any(x in t for x in ("each", "/ea", " per roll", "roll")):
        return "ea"
    if any(x in t for x in ("/lb", "per lb", "per pound")):
        return "lb"
    if "roll" in t:
        return "ea"
    return "lb"


def _canonical_web_special_key(title: str) -> str:
    t = title.lower()
    if "lobster roll" in t:
        return "lobster_roll"
    if "chowder" in t:
        return "chowder"
    if "halibut" in t:
        return "halibut"
    if "scallop" in t:
        return "scallops"
    if "clam" in t:
        return "clams"
    if "shrimp" in t:
        return "shrimp"
    if "haddock" in t:
        return "haddock"
    if "salmon" in t:
        return "salmon"
    return re.sub(r"[^a-z0-9]+", "_", t).strip("_")[:80]


def parse_web_catalog(html: str) -> List[ParsedWebRow]:
    """Extract (kind, key, price, unit, snippet) tuples from a web catalog page."""
    rows: List[ParsedWebRow] = []
    title_matches = list(_TITLE_RE.finditer(html))
    price_matches = list(_PRICE_BLOCK_RE.finditer(html))

    for tm in title_matches:
        title = _strip_tags(tm.group(1))
        next_title_pos = html.find("<h2", tm.end())
        if next_title_pos == -1:
            next_title_pos = len(html)
        candidate_prices = [
            p for p in price_matches if tm.end() <= p.start() < next_title_pos
        ]
        if not candidate_prices:
            continue
        price_str = candidate_prices[0].group(1).replace(",", "")
        try:
            price = float(price_str)
        except ValueError:
            continue

        title_l = title.lower()
        if any(kw in title_l for kw in (
            "lobster meat", "picked meat", "cooked", "bisque",
            "mac and cheese", "ravioli", "lobster mac",
        )):
            continue

        unit = _detect_unit(title)
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
            from parse_prices import _find_oyster_grade_in_clause  # type: ignore
            grade = _find_oyster_grade_in_clause(title)
            oyster_tier = grade or "oyster"
            rows.append(("oyster_tier", oyster_tier, price, unit, title))
            continue

        if lobster_tier:
            rows.append(("lobster_tier", lobster_tier, price, "lb", title))
        else:
            key = _canonical_web_special_key(title)
            rows.append(("special", key, price, unit, title))
    return rows


def fetch_and_parse(url: str) -> List[ParsedWebRow]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
        return parse_web_catalog(html)
    except Exception as e:
        print(f"  [web parse error] {url}: {type(e).__name__}: {e}", flush=True)
        return []
