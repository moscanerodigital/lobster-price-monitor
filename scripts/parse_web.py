"""Web catalog parser — extracts product name + price from WooCommerce HTML."""

from __future__ import annotations

import html as html_module
import json
import re
import urllib.request
from dataclasses import dataclass
from typing import List, Literal, Tuple

_PRICE_BLOCK_RE = re.compile(
    r'<span[^>]*class="[^"]*woocommerce-Price-amount[^"]*"[^>]*>'
    r"(?:\s*<bdi>)?\s*"
    r'<span[^>]*class="[^"]*currencySymbol[^"]*"[^>]*>(?:\$|&#0?36;)</span>\s*'
    r"([\d.,]+)\s*"
    r"(?:</bdi>)?\s*</span>",
    re.DOTALL | re.IGNORECASE,
)
_TITLE_RE = re.compile(
    r'<h2[^>]*class="[^"]*(?:woocommerce-loop-product__title|entry-title[^"]*product_title)[^"]*"[^>]*>\s*(.+?)\s*</h2>',
    re.DOTALL,
)
_VARIATIONS_RE = re.compile(
    r'data-product_variations="(\[.*?\])"',
    re.DOTALL,
)

PARSER_VERSION = "parse_web/1.6"

ParsedWebRow = Tuple[
    Literal["lobster_tier", "oyster_tier", "special"],
    str,
    float,
    str,
    str,
]

_HARBOR_SIZE_MAP = {
    "chix": "chicks",
    "1-14-lb": "1.25lb",
    "1-12-lb": "1.5lb",
}

_HARBOR_SIZE_LABELS = {
    "chix": "1 lb (chix)",
    "1-14-lb": "1¼ lb",
    "1-12-lb": "1½ lb",
}

# Harbor WooCommerce variation prices are per lobster; weights from live catalog.
_HARBOR_SIZE_WEIGHT_LB = {
    "chix": 1.1,
    "1-14-lb": 1.35,
    "1-12-lb": 1.65,
}


@dataclass
class WebCatalogRow:
    """Full parsed row with provenance for persistence and board display."""

    kind: str
    key: str
    price: float
    unit: str
    snippet: str
    raw_price: float | None = None
    price_high: float | None = None
    price_display_type: str = "single"  # single | range | normalized | size_specific
    normalization_weight_lb: float | None = None
    catalog_title: str = ""
    normalized_price: float | None = None
    display_price: float | None = None
    display_unit: str | None = None
    display_price_high: float | None = None
    shell_tier: str | None = None

    def as_tuple(self) -> ParsedWebRow:
        return (self.kind, self.key, self.price, self.unit, self.snippet)  # type: ignore[return-value]

    def as_parsed_tuple(self) -> ParsedWebRow:
        return self.as_tuple()

    def meta(self) -> dict:
        out: dict = {
            "parser_version": PARSER_VERSION,
            "price_display_type": self.price_display_type,
            "catalog_title": self.catalog_title or self.snippet.split(" (catalog")[0],
        }
        if self.raw_price is not None:
            out["raw_price"] = self.raw_price
        if self.price_high is not None:
            out["price_high"] = self.price_high
            out["raw_price_high"] = self.price_high
        if self.price_display_type == "range":
            out["price_is_range"] = True
        if self.normalization_weight_lb is not None:
            out["normalization_weight_lb"] = self.normalization_weight_lb
            out["normalization_weight"] = self.normalization_weight_lb
        if self.normalized_price is not None:
            out["normalized_price"] = self.normalized_price
        if self.display_price is not None:
            out["display_price"] = self.display_price
        if self.display_unit is not None:
            out["display_unit"] = self.display_unit
        if self.display_price_high is not None:
            out["display_price_high"] = self.display_price_high
        if self.shell_tier is not None:
            out["shell_tier"] = self.shell_tier
        return out

    def persist_metadata(self) -> dict:
        out = self.meta()
        if self.price_high is not None:
            out["raw_price_high"] = self.price_high
        if self.price_display_type == "range":
            out["price_is_range"] = True
        if self.normalization_weight_lb is not None:
            out["normalization_weight"] = self.normalization_weight_lb
        return out


def _strip_tags(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s).strip()


def _slug_key(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")[:80]


def _detect_unit(title: str) -> str:
    t = title.lower()
    if any(x in t for x in ("doz", "dozen", "/dz")):
        return "doz"
    if "oyster" in t and not any(x in t for x in (" lb", "/lb", "pint")):
        return "doz"
    if any(x in t for x in ("each", "/ea", " per roll", "roll")):
        return "ea"
    if any(x in t for x in ("/lb", "per lb", "per pound")):
        return "lb"
    if "roll" in t:
        return "ea"
    return "lb"


def _lobster_weight_from_title(title: str) -> float | None:
    t = title.lower()
    if "1.25" in title or "1 1/4" in title or "1¼" in title:
        return 1.25
    if "1.5" in title or "1 1/2" in title or "1½" in title:
        return 1.5
    if "1.75" in title or "1 3/4" in title or "1¾" in title:
        return 1.75
    if "1lb" in t or "1 lb" in t or "(1 lb" in t:
        return 1.0
    return None


_ICONIC_SPECIAL_KEYS: dict[str, str] = {
    "lobster roll": "lobster_roll",
    "chowder": "chowder",
    "bisque": "bisque",
}


def _species_key_from_title(title: str) -> str | None:
    """Broad species bucket for price bands — not used as the catalog row key."""
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
    if "char" in t:
        return "arctic_char"
    if "bluefish" in t:
        return "bluefish"
    if "sole" in t:
        return "sole"
    if "flounder" in t:
        return "flounder"
    if "hake" in t:
        return "hake"
    if "swordfish" in t:
        return "swordfish"
    if "tuna" in t:
        return "tuna"
    if "cod" in t:
        return "cod"
    if "medley" in t:
        return "fish_medley"
    if "bisque" in t:
        return "bisque"
    if "smoked" in t:
        return "smoked"
    return None


def _canonical_web_special_key(title: str) -> str:
    """Unique per catalog line — keeps salmon/tuna varieties distinct on the board."""
    t = title.lower()
    for phrase, key in _ICONIC_SPECIAL_KEYS.items():
        if phrase in t:
            return key
    slug = re.sub(r"^fresh\s+", "", t)
    slug = re.sub(r"\s+per\s+lb$", "", slug)
    slug = re.sub(r"[^a-z0-9]+", "_", slug).strip("_")[:80]
    if slug:
        return slug
    return _species_key_from_title(title) or "special"


def _parse_price_values(candidate_prices: list) -> list[float]:
    values: list[float] = []
    for p in candidate_prices:
        try:
            values.append(float(p.group(1).replace(",", "")))
        except ValueError:
            continue
    return values


def _range_snippet(title: str, low: float, high: float, unit: str) -> str:
    unit_label = "/lb" if unit == "lb" else f"/{unit}"
    return f"{title} (catalog ${low:.2f}–${high:.2f}{unit_label} range)"


def _shell_tier_from_title(title_l: str) -> str | None:
    if "hard" in title_l:
        return "hard_shell"
    if "soft" in title_l:
        return "soft_shell"
    if "chick" in title_l:
        return "chicks"
    return None


def _lobster_tier_from_title(title: str) -> str | None:
    title_l = title.lower()
    if "1.25" in title or "1 1/4" in title or "1¼" in title:
        tier = "1.25lb"
    elif "1.5" in title or "1 1/2" in title or "1½" in title:
        tier = "1.5lb"
    elif "1.75" in title or "1 3/4" in title or "1¾" in title:
        tier = "1.75lb"
    elif "1lb" in title_l or "1 lb" in title_l or "(1 lb" in title_l:
        tier = "1lb"
    elif "2 lb" in title_l or "2lb" in title_l or "jumbo" in title_l:
        tier = "2lb_plus"
    else:
        tier = _shell_tier_from_title(title_l)
    return tier


def _parse_variations(block: str) -> list[dict]:
    m = _VARIATIONS_RE.search(block)
    if not m:
        return []
    try:
        return json.loads(html_module.unescape(m.group(1)))
    except json.JSONDecodeError:
        return []


def _variation_tier_key(size_tier: str, shell: str | None) -> str:
    """Unique tier key per shell + size (avoids hard/soft chicks collision)."""
    if shell:
        return f"{size_tier}_{shell}"
    return size_tier


def _harbor_variation_row(
    title: str,
    *,
    tier_key: str,
    size_label: str,
    catalog_total: float,
    weight_lb: float,
    shell: str | None,
) -> WebCatalogRow:
    """Harbor Fish sells whole lobsters — normalize catalog total to $/lb."""
    normalized = round(catalog_total / weight_lb, 2)
    snippet = (
        f"{title} — {size_label} "
        f"(${catalog_total:.2f} per lobster; ~${normalized:.2f}/lb)"
    )
    return WebCatalogRow(
        kind="lobster_tier",
        key=tier_key,
        price=normalized,
        unit="lb",
        snippet=snippet,
        raw_price=catalog_total,
        normalized_price=normalized,
        price_display_type="normalized",
        normalization_weight_lb=weight_lb,
        catalog_title=title,
        display_price=normalized,
        display_unit="lb",
        shell_tier=shell,
    )


def _rows_from_variations(title: str, variations: list[dict]) -> List[WebCatalogRow]:
    """Harbor Fish style size-specific lobster prices from WooCommerce variations."""
    title_l = title.lower()
    if "lobster" not in title_l:
        return []
    shell = _shell_tier_from_title(title_l)
    rows: List[WebCatalogRow] = []
    for var in variations:
        size_slug = var.get("attributes", {}).get("attribute_pa_size", "")
        tier = _HARBOR_SIZE_MAP.get(size_slug)
        if not tier:
            continue
        price = var.get("display_price") or var.get("display_regular_price")
        if price is None:
            continue
        catalog_total = float(price)
        weight_raw = var.get("weight")
        weight_lb = (
            float(weight_raw)
            if weight_raw not in (None, "", 0, "0")
            else _HARBOR_SIZE_WEIGHT_LB.get(size_slug, 1.0)
        )
        if weight_lb <= 0:
            continue
        size_label = _HARBOR_SIZE_LABELS.get(size_slug, size_slug.replace("-", " "))
        tier_key = _variation_tier_key(tier, shell)
        rows.append(
            _harbor_variation_row(
                title,
                tier_key=tier_key,
                size_label=size_label,
                catalog_total=catalog_total,
                weight_lb=weight_lb,
                shell=shell,
            )
        )
    return rows


def _pine_tree_lobster_row(
    title: str,
    lobster_tier: str,
    catalog_total: float,
    weight: float,
    shell: str | None,
) -> WebCatalogRow:
    """Pine Tree sells whole lobsters by weight class — normalize catalog total to $/lb."""
    normalized = round(catalog_total / weight, 2)
    snippet = f"{title} (${catalog_total:.2f} per lobster; ~${normalized:.2f}/lb)"
    return WebCatalogRow(
        kind="lobster_tier",
        key=lobster_tier,
        price=normalized,
        unit="lb",
        snippet=snippet,
        raw_price=catalog_total,
        normalized_price=normalized,
        price_display_type="normalized",
        normalization_weight_lb=weight,
        catalog_title=title,
        display_price=normalized,
        display_unit="lb",
        shell_tier=shell,
    )


def parse_web_catalog_rows(html: str) -> List[WebCatalogRow]:
    """Extract full catalog rows with raw/normalized/range/size provenance."""
    rows: List[WebCatalogRow] = []
    title_matches = list(_TITLE_RE.finditer(html))

    for tm in title_matches:
        title = _strip_tags(tm.group(1))
        next_title_pos = html.find("<h2", tm.end())
        if next_title_pos == -1:
            next_title_pos = len(html)
        block = html[tm.end() : next_title_pos]
        candidate_prices = list(_PRICE_BLOCK_RE.finditer(block))
        price_values = _parse_price_values(candidate_prices)

        title_l = title.lower()
        if any(
            kw in title_l
            for kw in (
                "lobster meat",
                "picked meat",
                "cooked",
                "bisque",
                "mac and cheese",
                "ravioli",
                "lobster mac",
                "fish medley",
                "frozen fish",
            )
        ):
            continue

        variations = _parse_variations(block)
        if variations and "lobster" in title_l:
            var_rows = _rows_from_variations(title, variations)
            if var_rows:
                rows.extend(var_rows)
                continue

        if not price_values:
            continue

        low_price = min(price_values)
        high_price = max(price_values)
        is_range = len(price_values) >= 2 and high_price > low_price
        unit = _detect_unit(title)

        if "oyster" in title_l:
            from parse_prices import _find_oyster_grade_in_clause, oyster_variety_label  # type: ignore

            grade = _find_oyster_grade_in_clause(title)
            named = oyster_variety_label(title)
            if grade:
                oyster_tier = grade
            elif named:
                oyster_tier = _slug_key(named)
            else:
                oyster_tier = "oyster"
            if "shuck" in title_l and (
                "pkg" in title_l or "package" in title_l or re.search(r"\d+\s*lb\s*pkg", title_l)
            ):
                oyster_tier = grade or "shucked"
                unit = "pkg"
            elif "shuck" in title_l and "/lb" in title_l:
                oyster_tier = grade or "shucked"
                unit = "lb"
            else:
                unit = _detect_unit(title)
            if is_range:
                rows.append(
                    WebCatalogRow(
                        kind="oyster_tier",
                        key=oyster_tier,
                        price=low_price,
                        unit=unit,
                        snippet=_range_snippet(title, low_price, high_price, unit),
                        raw_price=low_price,
                        price_high=high_price,
                        display_price=low_price,
                        display_unit=unit,
                        display_price_high=high_price,
                        price_display_type="range",
                        catalog_title=title,
                    )
                )
            else:
                rows.append(
                    WebCatalogRow(
                        kind="oyster_tier",
                        key=oyster_tier,
                        price=low_price,
                        unit=unit,
                        snippet=title,
                        raw_price=low_price,
                        display_price=low_price,
                        display_unit=unit,
                        price_display_type="single",
                        catalog_title=title,
                    )
                )
            continue

        lobster_tier = _lobster_tier_from_title(title) if "lobster" in title_l else None
        if lobster_tier:
            weight = _lobster_weight_from_title(title)
            shell = _shell_tier_from_title(title_l)
            if shell and lobster_tier in {"1lb", "1.25lb", "1.5lb", "1.75lb", "2lb_plus"}:
                lobster_tier = f"{lobster_tier}_{shell}"
            if weight and weight > 0:
                rows.append(
                    _pine_tree_lobster_row(
                        title,
                        lobster_tier,
                        low_price,
                        weight,
                        shell,
                    )
                )
            elif is_range:
                rows.append(
                    WebCatalogRow(
                        kind="lobster_tier",
                        key=lobster_tier,
                        price=low_price,
                        unit="lb",
                        snippet=_range_snippet(title, low_price, high_price, "lb"),
                        raw_price=low_price,
                        price_high=high_price,
                        display_price=low_price,
                        display_unit="lb",
                        display_price_high=high_price,
                        price_display_type="range",
                        catalog_title=title,
                        shell_tier=shell,
                    )
                )
            else:
                rows.append(
                    WebCatalogRow(
                        kind="lobster_tier",
                        key=lobster_tier,
                        price=low_price,
                        unit="lb",
                        snippet=title,
                        raw_price=low_price,
                        display_price=low_price,
                        display_unit="lb",
                        price_display_type="single",
                        catalog_title=title,
                        shell_tier=shell,
                    )
                )
        else:
            key = _canonical_web_special_key(title)
            if is_range:
                rows.append(
                    WebCatalogRow(
                        kind="special",
                        key=key,
                        price=low_price,
                        unit=unit,
                        snippet=_range_snippet(title, low_price, high_price, unit),
                        raw_price=low_price,
                        price_high=high_price,
                        display_price=low_price,
                        display_unit=unit,
                        display_price_high=high_price,
                        price_display_type="range",
                        catalog_title=title,
                    )
                )
            else:
                rows.append(
                    WebCatalogRow(
                        kind="special",
                        key=key,
                        price=low_price,
                        unit=unit,
                        snippet=title,
                        raw_price=low_price,
                        display_price=low_price,
                        display_unit=unit,
                        price_display_type="single",
                        catalog_title=title,
                    )
                )
    return rows


def parse_web_catalog(html: str) -> List[ParsedWebRow]:
    """Extract (kind, key, price, unit, snippet) tuples from a web catalog page."""
    return [row.as_tuple() for row in parse_web_catalog_rows(html)]


def fetch_and_parse(url: str) -> List[ParsedWebRow]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
        return parse_web_catalog(html)
    except Exception as e:
        print(f"  [web parse error] {url}: {type(e).__name__}: {e}", flush=True)
        return []
