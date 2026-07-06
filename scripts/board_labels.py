"""Special and oyster label helpers for board rendering."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from markets import MARKETS
from parse_prices import _canonical_special_key, _infer_unit_from_clause, oyster_variety_label

_SPECIAL_MAX_AGE = timedelta(days=7)
_MAX_SPECIALS_PER_MARKET = 14
_MAX_SPECIALS_TOTAL = 36

_SALVAGE_SPECIES = (
    "halibut",
    "haddock",
    "salmon",
    "tuna",
    "cod",
    "scallop",
    "clam",
    "crab",
    "char",
    "sole",
    "flounder",
    "hake",
    "swordfish",
    "shrimp",
    "bluefish",
    "monkfish",
    "mussel",
    "oyster",
    "lobster roll",
    "chowder",
    "bisque",
    "sea bass",
    "bass",
)

_SLASH_ABBREV_EXPANSIONS: dict[str, str] = {
    "lob": "Lobster",
    "crab": "Crab",
    "tuna": "Tuna",
    "cod": "Cod",
    "hadd": "Haddock",
    "scall": "Scallops",
    "shrimp": "Shrimp",
}


def _parse_ts(s: str) -> datetime | None:
    if not s:
        return None
    s = s.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _oyster_display_label(key: str, snippet: str = "", catalog_title: str = "") -> str:
    from board_render import label_for

    source = catalog_title or snippet
    named = oyster_variety_label(source)
    if named:
        grade = label_for(key) if key not in {"oyster", "named_variety"} else None
        if grade and grade not in {"Oysters", "Named Variety"}:
            return f"{named} {grade}"
        return named
    if key == "named_variety":
        cleaned = re.sub(r"\b(?:oysters?|per\s+dozen|doz|dz)\b", "", source, flags=re.I)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" -–—•")
        if cleaned and len(cleaned) > 2:
            return cleaned[:48]
    if key == "oyster" and catalog_title:
        cleaned = re.sub(r"\s+", " ", catalog_title).strip()
        if cleaned and "oyster" in cleaned.lower():
            return cleaned[:48]
    if key == "shucked" and catalog_title:
        return "Shucked (1 lb pkg)"
    label = label_for(key)
    return label if label != "Oysters" or not source else "Oysters"


def _oyster_row_secondary(label: str, unit: str) -> str:
    """Unit-aware oyster sublabel for grouped chalkboard rows."""
    clean = label.strip()
    if unit == "ea":
        return clean if clean.lower() not in {"oysters", "named variety", ""} else "each"
    if unit == "doz":
        return clean if clean.lower() not in {"oysters", "named variety", ""} else "per dozen"
    return clean


def _is_clean_special_row(row: dict) -> bool:
    """Drop FB-search snippets that mash multiple catalog lines into one row."""
    if row.get("catalog_title"):
        return True
    snippet = str(row.get("snippet", ""))
    if len(snippet) > 90:
        return False
    if snippet.count("$") > 1:
        return False
    if re.search(r"🐟|🐚|🦞", snippet):
        return False
    if "\n" in snippet:
        return False
    if "•" in snippet or "·" in snippet:
        return False
    if snippet.rstrip().endswith(","):
        return False
    if re.search(r"(?:^|[\s•])(?:\d+(?:\.\d+)?)\s*/\s*lb\.?", snippet, re.I):
        return False
    if re.search(r"\b(mediums?|large|jumbo|chix)\s*\$", snippet, re.I):
        return False
    if re.search(r"lobsters?\s+starting\s+at", snippet, re.I):
        return False
    return True


def _salvage_mashup_special_rows(row: dict) -> list[dict]:
    """Split multi-line FB menu snippets into one row per clean price line."""
    if row.get("kind") != "special" or _is_clean_special_row(row):
        return [row]
    salvaged: list[dict] = []
    for line in re.split(r"[\n\r]+", str(row.get("snippet", ""))):
        clean_line = re.sub(r"^[•·🐟🐚🦞🦪\s]+", "", line).strip()
        if not clean_line:
            continue
        if re.search(r"\b(obster|ddock|esh cod)\b", clean_line, re.I):
            continue
        line_l = clean_line.lower()
        if not any(kw in line_l for kw in _SALVAGE_SPECIES):
            continue
        price_match = re.search(
            r"\$?\s*(\d+(?:\.\d{1,2})?)\s*(?:/(?:lb|doz|ea)|(?:lb|ea)\b|each)",
            clean_line,
            re.I,
        )
        if not price_match:
            continue
        parsed_price = float(price_match.group(1))
        if parsed_price < 5.0 or parsed_price > 75.0:
            continue
        labelish = re.sub(r"\$[\d.,]+.*$", "", clean_line, flags=re.I).strip()
        if len(labelish) < 4 or not re.search(r"[a-z]{3,}", labelish, re.I):
            continue
        unit_match = re.search(r"/\s*(lb|doz|ea)\b|(?:lb|ea)\b|each", clean_line, re.I)
        unit = "lb"
        if unit_match:
            u = unit_match.group(1) or unit_match.group(0)
            unit = u.lower().replace("each", "ea")
        else:
            unit = _infer_unit_from_clause(clean_line)
        child = {
            **row,
            "snippet": clean_line,
            "price": parsed_price,
            "unit": unit,
            "key": _canonical_special_key(clean_line, None),
        }
        if child.get("display_price") is not None:
            child["display_price"] = parsed_price
        if child.get("display_unit"):
            child["display_unit"] = unit
        if not _is_clean_special_row(child):
            continue
        if not _special_row_coherent(child):
            continue
        label = _special_display_label(child, child.get("key", ""))
        if _is_publishable_special_label(label, row=child):
            salvaged.append(child)
    return salvaged if salvaged else [row]


def _expand_special_rows(rows: list[dict]) -> list[dict]:
    out: list[dict] = []
    for row in rows:
        if row.get("kind") == "special":
            out.extend(_salvage_mashup_special_rows(row))
        else:
            out.append(row)
    return out


def _is_stale_special(row: dict) -> bool:
    if row.get("kind") != "special":
        return False
    dt = _parse_ts(str(row.get("observed_at", "")))
    if dt is None:
        return row.get("source") in ("google_cse", "duckduckgo", "facebook_search")
    age = datetime.now(timezone.utc) - dt.astimezone(timezone.utc)
    return age > _SPECIAL_MAX_AGE


def _is_publishable_special_label(label: str, *, row: dict | None = None) -> bool:
    if not label:
        return False
    if row and row.get("catalog_title"):
        title = str(row["catalog_title"]).strip()
        if len(title) >= 4:
            return True
    if len(label) < 3:
        return False
    if len(label) == 3 and label.lower() not in {"cod", "sea", "eel"}:
        return False
    if label.rstrip().endswith("$"):
        return False
    if re.search(r"\b(obster|ddock|esh cod)\b", label, re.I):
        return False
    if _is_cryptic_slash_label(label):
        return False
    return True


def _species_keys_in_text(text: str) -> set[str]:
    """Canonical special keys mentioned in snippet or catalog title."""
    from parse_prices import _CANONICAL_SPECIAL_MAP

    found: set[str] = set()
    text_l = text.lower()
    for pattern, canonical in _CANONICAL_SPECIAL_MAP:
        if re.search(pattern, text_l, re.IGNORECASE):
            found.add(canonical)
    return found


def _special_row_coherent(row: dict) -> bool:
    """Reject FB rows where parsed key disagrees with the product named in the snippet."""
    if row.get("catalog_title"):
        return True
    snippet = str(row.get("snippet", "")).strip()
    if not snippet:
        return True
    species = _species_keys_in_text(snippet)
    key = str(row.get("key", ""))
    if not species:
        return True
    if key in species:
        return True
    return False


def _format_special_freshness(ts: str, source: str) -> str:
    """Compact freshness badge — only when it adds signal."""
    dt = _parse_ts(ts)
    if not dt:
        return ""
    now = datetime.now(timezone.utc)
    age = now - dt.astimezone(timezone.utc)
    is_fb = source not in ("web", "manual", "reference")
    if age < timedelta(hours=30):
        return ""
    if age < timedelta(days=3):
        day = dt.astimezone().strftime("%a")
        return f"{day} · FB" if is_fb else day
    stamp = dt.astimezone().strftime("%b %-d").replace(" 0", " ")
    return f"{stamp} · FB" if is_fb else stamp


def _drop_stale_fb_specials_when_web_fresh(rows: list[dict]) -> list[dict]:
    """Prefer Jul 6 web catalog rows over Jul 4–5 FB search snippets for the same market."""
    now = datetime.now(timezone.utc)
    web_fresh: set[str] = set()
    for row in rows:
        if row.get("kind") != "special" or row.get("source") != "web":
            continue
        dt = _parse_ts(str(row.get("observed_at", "")))
        if dt and (now - dt.astimezone(timezone.utc)) <= timedelta(hours=48):
            web_fresh.add(str(row.get("market", "")))

    if not web_fresh:
        return rows

    kept: list[dict] = []
    for row in rows:
        if row.get("kind") != "special":
            kept.append(row)
            continue
        market = str(row.get("market", ""))
        if market not in web_fresh or row.get("source") == "web":
            kept.append(row)
            continue
        dt = _parse_ts(str(row.get("observed_at", "")))
        if dt is None or (now - dt.astimezone(timezone.utc)) <= timedelta(hours=48):
            kept.append(row)
            continue
    return kept


def _expand_slash_abbrev(label: str) -> str:
    """Turn cryptic FB keys like Lob/crab into readable board copy."""
    if "/" not in label:
        return label
    parts = [p.strip() for p in label.split("/") if p.strip()]
    if not parts:
        return label
    expanded = [
        _SLASH_ABBREV_EXPANSIONS.get(p.lower(), p.strip().title()) for p in parts
    ]
    return " & ".join(expanded)


def _is_cryptic_slash_label(label: str) -> bool:
    """Unreadable slash abbreviations without a catalog title."""
    if "/" not in label:
        return False
    if len(label) >= 12:
        return False
    parts = [p.strip() for p in label.split("/") if p.strip()]
    return bool(parts) and all(len(p) <= 5 for p in parts)


def _special_display_label(row: dict, fallback: str) -> str:
    """Customer-facing special name — prefer catalog title, else clean snippet/key."""
    if row.get("catalog_title"):
        title = str(row["catalog_title"])
    else:
        title = str(row.get("snippet") or fallback)
    title = re.sub(r"\s*\(\s*\d[^)]*\)", "", title).strip()
    title = re.sub(r"^[•·\-]\s*", "", title).strip()
    colon_match = re.match(r"^(.+?):\s*\$", title)
    if colon_match:
        title = colon_match.group(1).strip()
    title = re.sub(
        r"\s*\$[\d.,]+(?:\s*/?\s*(?:lb|ea|doz|each|pint|pints|quart)\.?)?\s*$",
        "",
        title,
        flags=re.I,
    ).strip()
    title = re.sub(
        r"\s+\$[\d.,]+(?:\s*/?\s*(?:lb|ea|doz|each|pint|pints|quart)\.?)?",
        "",
        title,
        flags=re.I,
    ).strip()
    title = re.sub(r"\s*\d+(?:\.\d+)?\s*lb\.?\s*$", "", title, flags=re.I).strip()
    title = re.sub(r"\s*\$\s*$", "", title).strip()
    title = re.sub(r"\s+(?:are|is)\s*$", "", title, flags=re.I).strip()
    title = re.sub(r"\s*[-–—]\s*$", "", title).strip()
    if title.lower().startswith("fresh "):
        title = title[6:].strip()
    key = str(row.get("key", ""))
    if key in {"clams", "steamers"} and "steamer" in title.lower():
        title = "Steamer clams"
    if _is_cryptic_slash_label(title):
        title = _expand_slash_abbrev(title)
    return title or fallback


def _special_item_rank(item: dict) -> tuple:
    key = item.get("key", "")
    iconic = key in ("lobster_roll", "chowder", "bisque")
    return (
        0 if iconic else 1,
        1 if item.get("price_is_range") else 0,
        -int(item.get("confidence", 0)),
        item.get("sort_price", item.get("price", 0)),
    )


def _special_freshness_rank(item: dict) -> tuple:
    return (
        item.get("observed_at", ""),
        _special_item_rank(item),
    )


def _cap_specials_by_market(items: list[dict]) -> list[dict]:
    """Keep up to N specials per market, max total — preserve every market with data."""
    if not items:
        return []
    by_market: dict[str, list[dict]] = {}
    for item in items:
        by_market.setdefault(item.get("market", ""), []).append(item)
    for market_items in by_market.values():
        market_items.sort(key=_special_freshness_rank, reverse=True)

    market_order = [m["name"] for m in MARKETS if m["name"] in by_market]
    for name in by_market:
        if name not in market_order:
            market_order.append(name)

    capped: list[dict] = []
    if len(market_order) * _MAX_SPECIALS_PER_MARKET <= _MAX_SPECIALS_TOTAL:
        for name in market_order:
            capped.extend(by_market[name][:_MAX_SPECIALS_PER_MARKET])
    else:
        per_market_idx = {name: 0 for name in market_order}
        while len(capped) < _MAX_SPECIALS_TOTAL:
            added = False
            for name in market_order:
                idx = per_market_idx[name]
                if idx < len(by_market[name]) and idx < _MAX_SPECIALS_PER_MARKET:
                    capped.append(by_market[name][idx])
                    per_market_idx[name] += 1
                    added = True
                    if len(capped) >= _MAX_SPECIALS_TOTAL:
                        break
            if not added:
                break

    capped.sort(
        key=lambda x: (
            market_order.index(x.get("market", "")) if x.get("market", "") in market_order else 99,
            _special_item_rank(x),
        ),
    )
    return capped
