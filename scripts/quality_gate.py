"""AAA quality gates — source quality, parse confidence, plausibility, freshness."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from parse_prices import (
    ParsedRow,
    _clause_of,
    _find_special_kw,
)

SOURCE_QUALITY: dict[str, float] = {
    "web": 1.0,
    "facebook": 0.9,
    "google_cse": 0.7,
    "duckduckgo": 0.5,
}

SPECIALS_CONFIDENCE_THRESHOLD = 70
TIER_CONFIDENCE_THRESHOLD = 60
MIN_SOURCE_QUALITY = 0.5

# Price bands: (min, max) per kind or (kind, key)
_PRICE_BANDS: dict[str, tuple[float, float]] = {
    "lobster_tier": (4.0, 25.0),
    "oyster_tier": (10.0, 50.0),
}
_SPECIAL_BANDS: dict[str, tuple[float, float]] = {
    "lobster_roll": (12.0, 45.0),
    "roll": (12.0, 45.0),
    "chowder": (6.0, 20.0),
    "bisque": (8.0, 25.0),
}
_DEFAULT_SPECIAL_BAND = (6.0, 40.0)
_DEFAULT_EA_BAND = (8.0, 45.0)

CANONICAL_SPECIAL_KEYS = {
    "halibut", "scallops", "clams", "shrimp", "haddock", "salmon", "cod",
    "pollock", "tuna", "swordfish", "chowder", "bisque", "lobster_roll",
    "roll", "crab", "smoked", "stew", "mac", "bake", "ravioli",
}


@dataclass
class GatedRow:
    kind: str
    key: str
    price: float
    unit: str
    snippet: str
    confidence: int
    source_quality: float
    gate_passed: bool
    reject_reason: str | None


def source_quality_score(source: str) -> float:
    return SOURCE_QUALITY.get(source, 0.3)


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


def _is_fresh(observed_at: str, source: str) -> tuple[bool, str | None]:
    if source == "web":
        return True, None
    dt = _parse_observed_at(observed_at)
    if dt is None:
        if source in ("google_cse", "duckduckgo"):
            return False, "missing_timestamp"
        return True, None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    age = datetime.now(timezone.utc) - dt.astimezone(timezone.utc)
    if age > timedelta(days=7):
        return False, "stale_post"
    return True, None


def _price_in_band(kind: str, key: str, price: float, unit: str) -> tuple[bool, str | None]:
    if kind == "lobster_tier":
        lo, hi = _PRICE_BANDS["lobster_tier"]
        if unit != "lb" or not (lo <= price <= hi):
            return False, f"price_out_of_band:{price}"
        return True, None
    if kind == "oyster_tier":
        lo, hi = _PRICE_BANDS["oyster_tier"]
        if unit == "doz" and lo <= price <= hi:
            return True, None
        if unit == "lb" and lo / 12 <= price <= hi / 12:
            return True, None
        return False, f"price_out_of_band:{price}"
    if kind == "special":
        if unit == "ea":
            lo, hi = _DEFAULT_EA_BAND
        elif key in _SPECIAL_BANDS:
            lo, hi = _SPECIAL_BANDS[key]
        else:
            lo, hi = _DEFAULT_SPECIAL_BAND
        if not (lo <= price <= hi):
            return False, f"price_out_of_band:{price}"
        return True, None
    return True, None


def _has_explicit_unit(snippet: str, unit: str) -> bool:
    s = snippet.lower()
    if unit == "lb":
        return any(x in s for x in ("/lb", "per pound", "per lb", " a pound", " lb"))
    if unit == "doz":
        return any(x in s for x in ("/doz", "per dozen", " a dozen", " dz", " doz", " dozen"))
    if unit == "ea":
        return any(x in s for x in ("each", "/ea", "/roll", "per roll", " ea"))
    return False


def _keyword_in_clause(text: str, price_pos: int, kw: str) -> bool:
    clause = _clause_of(text, price_pos)
    return kw.lower() in clause.lower()


def score_row(
    row: ParsedRow,
    *,
    source: str,
    observed_at: str,
    full_text: str = "",
    price_pos: int | None = None,
    bare_price: bool = False,
) -> GatedRow:
    kind, key, price, unit, snippet = row
    sq = source_quality_score(source)
    confidence = 0

    if sq < MIN_SOURCE_QUALITY:
        return GatedRow(
            kind=kind, key=key, price=price, unit=unit, snippet=snippet,
            confidence=0, source_quality=sq, gate_passed=False,
            reject_reason="low_source_quality",
        )

    if _has_explicit_unit(snippet, unit):
        confidence += 40
    elif bare_price:
        confidence += 10
    else:
        confidence += 25

    kw = _find_special_kw(full_text, price_pos or 0) if full_text else None
    if kind == "lobster_tier":
        confidence += 20
    elif kind == "oyster_tier":
        confidence += 20
    elif kw and full_text and price_pos is not None and _keyword_in_clause(full_text, price_pos, kw):
        confidence += 30
    elif kw:
        confidence += 15

    if source == "web":
        confidence += 10

    if bare_price:
        confidence -= 30

    if kind == "special" and key not in CANONICAL_SPECIAL_KEYS and len(key) > 30:
        confidence -= 20

    confidence = max(0, min(100, confidence))

    fresh, fresh_reason = _is_fresh(observed_at, source)
    if not fresh:
        return GatedRow(
            kind=kind, key=key, price=price, unit=unit, snippet=snippet,
            confidence=confidence, source_quality=sq, gate_passed=False,
            reject_reason=fresh_reason,
        )

    in_band, band_reason = _price_in_band(kind, key, price, unit)
    if not in_band:
        return GatedRow(
            kind=kind, key=key, price=price, unit=unit, snippet=snippet,
            confidence=confidence, source_quality=sq, gate_passed=False,
            reject_reason=band_reason,
        )

    threshold = SPECIALS_CONFIDENCE_THRESHOLD if kind == "special" else TIER_CONFIDENCE_THRESHOLD
    if confidence < threshold:
        return GatedRow(
            kind=kind, key=key, price=price, unit=unit, snippet=snippet,
            confidence=confidence, source_quality=sq, gate_passed=False,
            reject_reason=f"low_confidence:{confidence}",
        )

    return GatedRow(
        kind=kind, key=key, price=price, unit=unit, snippet=snippet,
        confidence=confidence, source_quality=sq, gate_passed=True,
        reject_reason=None,
    )


def gate_rows(
    rows: list[ParsedRow],
    *,
    source: str,
    observed_at: str,
    full_text: str = "",
    parse_meta: list[dict] | None = None,
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
        )
        if gated.gate_passed:
            passed.append(gated)
        else:
            quarantined.append(gated)
    return passed, quarantined
