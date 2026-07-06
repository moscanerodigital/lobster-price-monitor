"""AAA quality gates — explicit Gate A / B / C pipeline.

Gate A (Source):      source quality score >= MIN_SOURCE_QUALITY
Gate B (Confidence):  parse confidence >= kind threshold, adjusted by source quality
Gate C (Plausibility): price in band + post freshness

Rows must pass all three gates to surface. Failures are quarantined with the
first failing gate recorded as reject_reason.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from parse_prices import (
    ParsedRow,
    _clause_of,
    _find_special_kw,
    _find_special_kw_in_clause,
    is_specials_post,
)

SOURCE_QUALITY: dict[str, float] = {
    "web": 1.0,
    "facebook": 1.0,
    "facebook_search": 0.9,
    "reference": 0.95,
    "google_cse": 0.7,
    "duckduckgo": 0.5,
}

SPECIALS_CONFIDENCE_THRESHOLD = 70
TIER_CONFIDENCE_THRESHOLD = 60
MIN_SOURCE_QUALITY = 0.5
MIN_SPECIALS_ALERT_CONFIDENCE = 70
MIN_TIER_ALERT_CONFIDENCE = 60

_PRICE_BANDS: dict[str, tuple[float, float]] = {
    "lobster_tier": (4.0, 35.0),
    "oyster_tier": (10.0, 50.0),
}
_OYSTER_EACH_BAND = (0.75, 5.00)
_OYSTER_SHUCKED_PKG_BAND = (12.0, 40.0)

# Minimum credible $/lb for FB/search lobster tiers (2026 Maine retail).
LOBSTER_TIER_FLOORS: dict[str, float] = {
    "chicks": 7.50,
    "soft_shell": 8.00,
    "old_shell": 8.50,
    "hard_shell": 9.50,
    "select": 10.00,
    "1.125lb": 7.50,
    "1.25lb": 8.00,
    "1.5lb": 9.00,
    "1.75lb": 10.00,
    "2lb_plus": 11.00,
}
_DEFAULT_LOBSTER_FLOOR_LB = 8.00
# FB posts name their own $/lb — apply tier floors only to search snippets.
_TRUSTED_LOBSTER_SOURCES = frozenset({"web", "reference", "facebook"})
_SPECIAL_BANDS: dict[str, tuple[float, float]] = {
    "lobster_roll": (12.0, 45.0),
    "roll": (12.0, 45.0),
    "chowder": (6.0, 20.0),
    "bisque": (8.0, 25.0),
}
_DEFAULT_SPECIAL_BAND = (6.0, 40.0)
_DEFAULT_EA_BAND = (8.0, 45.0)

CANONICAL_SPECIAL_KEYS = {
    "halibut",
    "scallops",
    "clams",
    "shrimp",
    "haddock",
    "salmon",
    "cod",
    "pollock",
    "tuna",
    "swordfish",
    "chowder",
    "bisque",
    "lobster_roll",
    "roll",
    "crab",
    "smoked",
    "stew",
    "mac",
    "bake",
    "ravioli",
    "arctic_char",
    "bluefish",
    "sole",
    "flounder",
    "hake",
    "mussels",
    "monkfish",
    "fish_medley",
}

FB_MENU_SPECIALS_CONFIDENCE_BOOST = 15
# Menu posts with canonical species keys but no keyword window hit still need ≥70.
FB_MENU_CANONICAL_KEY_BOOST = 10


@dataclass
class GatedRow:
    kind: str
    key: str
    price: float
    unit: str
    snippet: str
    confidence: int
    raw_confidence: int
    source_quality: float
    gate_passed: bool
    gate_a_passed: bool
    gate_b_passed: bool
    gate_c_passed: bool
    reject_reason: str | None
    failed_gate: str | None = None


@dataclass
class GateStats:
    """Aggregate gate failure counts for run-log."""

    gate_a_failed: int = 0
    gate_b_failed: int = 0
    gate_c_failed: int = 0
    passed: int = 0

    def record(self, row: GatedRow) -> None:
        if row.gate_passed:
            self.passed += 1
        elif row.failed_gate == "A":
            self.gate_a_failed += 1
        elif row.failed_gate == "B":
            self.gate_b_failed += 1
        elif row.failed_gate == "C":
            self.gate_c_failed += 1

    def as_dict(self) -> dict:
        return {
            "gate_a_failed": self.gate_a_failed,
            "gate_b_failed": self.gate_b_failed,
            "gate_c_failed": self.gate_c_failed,
            "gate_passed": self.passed,
        }


def source_quality_score(source: str) -> float:
    return SOURCE_QUALITY.get(source, 0.3)


def min_confidence_for_kind(kind: str) -> int:
    return SPECIALS_CONFIDENCE_THRESHOLD if kind == "special" else TIER_CONFIDENCE_THRESHOLD


def special_band_key(key: str) -> str:
    """Map title-slug catalog keys (e.g. wild_pacific_salmon_fillet) to species bands."""
    if key in _SPECIAL_BANDS or key in CANONICAL_SPECIAL_KEYS:
        return key
    key_l = key.lower()
    for species in sorted(CANONICAL_SPECIAL_KEYS, key=len, reverse=True):
        if species in key_l:
            return species
    return key


def special_has_canonical_key(key: str) -> bool:
    band = special_band_key(key)
    return band in CANONICAL_SPECIAL_KEYS


def min_confidence_for_alert(kind: str) -> int:
    return MIN_SPECIALS_ALERT_CONFIDENCE if kind == "special" else MIN_TIER_ALERT_CONFIDENCE


def confidence_meets_alert_threshold(kind: str, confidence: int) -> bool:
    return confidence >= min_confidence_for_alert(kind)


def _parse_observed_at(observed_at: str) -> datetime | None:
    if not observed_at or not observed_at.strip():
        return None
    s = observed_at.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _gate_a_source(source: str) -> tuple[bool, float, str | None]:
    sq = source_quality_score(source)
    if sq < MIN_SOURCE_QUALITY:
        return False, sq, "gate_a:low_source_quality"
    return True, sq, None


def _has_explicit_unit(snippet: str, unit: str) -> bool:
    s = snippet.lower()
    if unit == "lb":
        return any(x in s for x in ("/lb", "per pound", "per lb", " a pound", " lb")) or bool(
            re.search(r"\d+lb\b", s)
        )
    if unit == "doz":
        return any(x in s for x in ("/doz", "per dozen", " a dozen", " dz", " doz", " dozen"))
    if unit == "ea":
        return any(x in s for x in ("each", "/ea", "/roll", "per roll", " ea"))
    return False


def _compute_raw_confidence(
    row: ParsedRow,
    *,
    source: str,
    full_text: str,
    price_pos: int | None,
    bare_price: bool,
    structured: bool,
) -> int:
    kind, key, _price, unit, snippet = row
    confidence = 0

    if _has_explicit_unit(snippet, unit):
        confidence += 40
    elif bare_price:
        confidence += 10
    else:
        confidence += 25

    kw = None
    if full_text and price_pos is not None:
        kw = _find_special_kw_in_clause(full_text, price_pos) or _find_special_kw(
            full_text, price_pos
        )

    if kind == "lobster_tier":
        confidence += 20
        if source in ("facebook", "facebook_search") and _has_explicit_unit(snippet, unit):
            confidence += 10
        if full_text and full_text.lower().count("/lb") >= 2:
            confidence += 10
    elif kind == "oyster_tier":
        confidence += 20
    elif kw and full_text and price_pos is not None:
        clause = _clause_of(full_text, price_pos)
        if kw.lower() in clause.lower():
            confidence += 30
        else:
            confidence += 15

    if source in ("web", "facebook", "facebook_search") or structured:
        confidence += 10
    if structured:
        confidence += 15
        if kind == "special" and special_has_canonical_key(key):
            confidence += 20

    if (
        kind == "special"
        and full_text
        and source in ("facebook", "facebook_search")
        and is_specials_post(full_text)
    ):
        confidence += FB_MENU_SPECIALS_CONFIDENCE_BOOST
        if special_has_canonical_key(key) and kw is None:
            confidence += FB_MENU_CANONICAL_KEY_BOOST

    if bare_price:
        confidence -= 30

    if kind == "special" and not special_has_canonical_key(key) and len(key) > 30:
        confidence -= 20

    return max(0, min(100, confidence))


def _gate_b_confidence(
    kind: str,
    raw_confidence: int,
    source_quality: float,
) -> tuple[bool, int, str | None]:
    # Source quality scales effective confidence (Gate A multiplier applied here)
    effective = int(round(raw_confidence * source_quality))
    threshold = min_confidence_for_kind(kind)
    if effective < threshold:
        return False, effective, f"gate_b:low_confidence:{effective}"
    return True, effective, None


def _price_in_band(kind: str, key: str, price: float, unit: str) -> tuple[bool, str | None]:
    if kind == "lobster_tier":
        lo, hi = _PRICE_BANDS["lobster_tier"]
        if unit == "lb" and lo <= price <= hi:
            return True, None
        # Whole-lobster catalog totals (Pine Tree): ~0.75–2.5 lb at market $/lb
        if unit == "ea" and (lo * 0.75) <= price <= (hi * 2.5):
            return True, None
        return False, f"gate_c:price_out_of_band:{price}"
    if kind == "oyster_tier":
        lo, hi = _PRICE_BANDS["oyster_tier"]
        if unit == "doz" and lo <= price <= hi:
            return True, None
        if unit == "ea":
            if key == "shucked" or "shuck" in key:
                slo, shi = _OYSTER_SHUCKED_PKG_BAND
                if slo <= price <= shi:
                    return True, None
            if _OYSTER_EACH_BAND[0] <= price <= _OYSTER_EACH_BAND[1]:
                return True, None
            return False, f"gate_c:price_out_of_band:{price}"
        if unit == "lb" and lo / 12 <= price <= hi / 12:
            return True, None
        return False, f"gate_c:price_out_of_band:{price}"
    if kind == "special":
        if unit == "ea":
            lo, hi = _DEFAULT_EA_BAND
        elif key in _SPECIAL_BANDS:
            lo, hi = _SPECIAL_BANDS[key]
        else:
            band_key = special_band_key(key)
            if band_key in _SPECIAL_BANDS:
                lo, hi = _SPECIAL_BANDS[band_key]
            else:
                lo, hi = _DEFAULT_SPECIAL_BAND
        if not (lo <= price <= hi):
            return False, f"gate_c:price_out_of_band:{price}"
        return True, None
    return True, None


def lobster_tier_floor_lb(key: str) -> float:
    """Return minimum credible $/lb for a lobster tier key."""
    base = key
    for suffix in ("_soft_shell", "_hard_shell"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            break
    if base in LOBSTER_TIER_FLOORS:
        return LOBSTER_TIER_FLOORS[base]
    if key in LOBSTER_TIER_FLOORS:
        return LOBSTER_TIER_FLOORS[key]
    return _DEFAULT_LOBSTER_FLOOR_LB


def _gate_c_lobster_market_floor(
    kind: str,
    key: str,
    price: float,
    unit: str,
    source: str,
    *,
    structured: bool,
) -> tuple[bool, str | None]:
    if kind != "lobster_tier" or unit != "lb":
        return True, None
    if structured or source in _TRUSTED_LOBSTER_SOURCES:
        # Absolute minimum even for direct FB posts (catches mis-parsed steamers/culls).
        if kind == "lobster_tier" and unit == "lb" and price < 6.0:
            return False, f"gate_c:lobster_below_market_floor:{price}<6.0"
        return True, None
    if price < 6.0:
        return False, f"gate_c:lobster_below_market_floor:{price}<6.0"
    floor = lobster_tier_floor_lb(key)
    if price < floor:
        return False, f"gate_c:lobster_below_market_floor:{price}<{floor}"
    return True, None


def _gate_c_plausibility(
    kind: str,
    key: str,
    price: float,
    unit: str,
    observed_at: str,
    source: str,
    *,
    structured: bool = False,
) -> tuple[bool, str | None]:
    if source == "web":
        in_band, band_reason = _price_in_band(kind, key, price, unit)
        if not in_band:
            return False, band_reason
        return True, None

    floor_ok, floor_reason = _gate_c_lobster_market_floor(
        kind,
        key,
        price,
        unit,
        source,
        structured=structured,
    )
    if not floor_ok:
        return False, floor_reason

    dt = _parse_observed_at(observed_at)
    if dt is None:
        if source in ("google_cse", "duckduckgo"):
            return False, "gate_c:missing_timestamp"
    else:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - dt.astimezone(timezone.utc)
        if age > timedelta(days=7):
            return False, "gate_c:stale_post"

    in_band, band_reason = _price_in_band(kind, key, price, unit)
    if not in_band:
        return False, band_reason
    return True, None


def score_row(
    row: ParsedRow,
    *,
    source: str,
    observed_at: str,
    full_text: str = "",
    price_pos: int | None = None,
    bare_price: bool = False,
    structured: bool = False,
) -> GatedRow:
    """Run row through Gate A → B → C. Stop at first failure."""
    kind, key, price, unit, snippet = row

    gate_a_ok, sq, gate_a_reason = _gate_a_source(source)
    if not gate_a_ok:
        return GatedRow(
            kind=kind,
            key=key,
            price=price,
            unit=unit,
            snippet=snippet,
            confidence=0,
            raw_confidence=0,
            source_quality=sq,
            gate_passed=False,
            gate_a_passed=False,
            gate_b_passed=False,
            gate_c_passed=False,
            reject_reason=gate_a_reason,
            failed_gate="A",
        )

    raw = _compute_raw_confidence(
        row,
        source=source,
        full_text=full_text,
        price_pos=price_pos,
        bare_price=bare_price,
        structured=structured,
    )
    gate_b_ok, effective, gate_b_reason = _gate_b_confidence(kind, raw, sq)
    if not gate_b_ok:
        return GatedRow(
            kind=kind,
            key=key,
            price=price,
            unit=unit,
            snippet=snippet,
            confidence=effective,
            raw_confidence=raw,
            source_quality=sq,
            gate_passed=False,
            gate_a_passed=True,
            gate_b_passed=False,
            gate_c_passed=False,
            reject_reason=gate_b_reason,
            failed_gate="B",
        )

    gate_c_ok, gate_c_reason = _gate_c_plausibility(
        kind,
        key,
        price,
        unit,
        observed_at,
        source,
        structured=structured,
    )
    if not gate_c_ok:
        return GatedRow(
            kind=kind,
            key=key,
            price=price,
            unit=unit,
            snippet=snippet,
            confidence=effective,
            raw_confidence=raw,
            source_quality=sq,
            gate_passed=False,
            gate_a_passed=True,
            gate_b_passed=True,
            gate_c_passed=False,
            reject_reason=gate_c_reason,
            failed_gate="C",
        )

    return GatedRow(
        kind=kind,
        key=key,
        price=price,
        unit=unit,
        snippet=snippet,
        confidence=effective,
        raw_confidence=raw,
        source_quality=sq,
        gate_passed=True,
        gate_a_passed=True,
        gate_b_passed=True,
        gate_c_passed=True,
        reject_reason=None,
        failed_gate=None,
    )


def gate_rows(
    rows: list[ParsedRow],
    *,
    source: str,
    observed_at: str,
    full_text: str = "",
    parse_meta: list[dict] | None = None,
    stats: GateStats | None = None,
) -> tuple[list[GatedRow], list[GatedRow]]:
    """Return (passed, quarantined) gated rows."""
    passed: list[GatedRow] = []
    quarantined: list[GatedRow] = []
    meta = parse_meta or [{}] * len(rows)
    for row, m in zip(rows, meta):
        gated = score_row(
            row,
            source=source,
            observed_at=observed_at,
            full_text=full_text,
            price_pos=m.get("price_pos"),
            bare_price=m.get("bare_price", False),
            structured=m.get("structured", False),
        )
        if stats is not None:
            stats.record(gated)
        if gated.gate_passed:
            passed.append(gated)
        else:
            quarantined.append(gated)
    return passed, quarantined


def passes_specials_alert_gate(
    text: str,
    special_items: list[dict],
    source: str,
) -> tuple[bool, str | None]:
    """Post-level AAA gate for specials Telegram alerts.

    Requirements (all must hold):
    1. Gate A: source quality >= MIN_SOURCE_QUALITY
    2. AC4b: is_specials_post(text) OR source is web (structured catalog)
    3. At least one special item with confidence >= MIN_SPECIALS_ALERT_CONFIDENCE
    4. Every item in special_items meets MIN_SPECIALS_ALERT_CONFIDENCE
    """
    sq = source_quality_score(source)
    if sq < MIN_SOURCE_QUALITY:
        return False, "gate_a:low_source_quality"

    if source != "web" and not is_specials_post(text):
        return False, "gate_b:not_specials_post"

    if not special_items:
        return False, "gate_b:no_special_items"

    for item in special_items:
        conf = int(item.get("confidence", 0))
        if conf < MIN_SPECIALS_ALERT_CONFIDENCE:
            return False, f"gate_b:item_below_threshold:{item.get('key')}:{conf}"

    return True, None
