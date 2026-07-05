"""Seafood board rendering — chalkboard-style terminal, HTML, and Telegram."""
from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from pathlib import Path

from markets import MARKETS
from state import read_json, read_jsonl, DATA_DIR

_LOBSTER_SIZE_ORDER = {
    "chicks_soft_shell": 0,
    "chicks_hard_shell": 1,
    "1lb_soft_shell": 2,
    "1lb_hard_shell": 3,
    "soft_shell": 4,
    "hard_shell": 5,
    "1.25lb_soft_shell": 10,
    "1.25lb_hard_shell": 11,
    "1.5lb_soft_shell": 12,
    "1.5lb_hard_shell": 13,
    "1.75lb_soft_shell": 14,
    "1.75lb_hard_shell": 15,
    "2lb_plus_soft_shell": 16,
    "2lb_plus_hard_shell": 17,
}

_ITEM_LABELS: dict[str, str] = {
    "chicks": "1 lb (chix)",
    "soft_shell": "Soft Shell",
    "old_shell": "Old Shell",
    "hard_shell": "Hard Shell",
    "select": "Select",
    "1.125lb": "1⅛ lb",
    "1.25lb": "1¼ lb",
    "1.5lb": "1½ lb",
    "1.75lb": "1¾ lb",
    "2lb_plus": "2 lb+",
    "1lb": "1 lb",
    "xl": "Extra Large",
    "jumbo": "Jumbo",
    "standard": "Standard",
    "single_select": "Single Select",
    "named_variety": "Named Variety",
    "oyster": "Oysters",
    "lobster_roll": "Lobster Roll",
    "halibut": "Halibut",
    "scallops": "Scallops",
    "clams": "Clams",
    "shrimp": "Shrimp",
    "haddock": "Haddock",
    "salmon": "Salmon",
    "arctic_char": "Arctic Char",
    "bluefish": "Bluefish",
    "sole": "Sole",
    "flounder": "Flounder",
    "hake": "Hake",
    "tuna": "Tuna",
    "swordfish": "Swordfish",
    "cod": "Cod",
    "mussels": "Mussels",
    "monkfish": "Monkfish",
    "fish_medley": "Fish Medley",
    "chowder": "Chowder",
    "bisque": "Bisque",
    "crab": "Crab",
}

_SECTION_META = {
    "lobster": ("🦞", "LIVE LOBSTER", "lb"),
    "oyster": ("🦪", "OYSTERS", "doz"),
    "special": ("🐟", "TODAY'S SPECIALS", ""),
}

# Hand-placed chalk: tilts, spacing, size bumps (deterministic per index)
_TAG_TILTS = (-2.1, 0.8, 2.4, -1.6, 2.9, -0.5, 1.7, -2.8, 0.3, 1.1, -1.9, 2.2)
_LETTER_SPACINGS = ("-0.02em", "0.01em", "0.04em", "-0.01em", "0.06em", "0em", "0.03em")
_PRICE_SCALES = (1.0, 1.12, 0.9, 1.18, 0.88, 1.05, 0.95, 1.15)
_SCATTER_OFFSETS = (
    (0, 0), (12, 4), (-6, 18), (20, -8), (-14, 28), (8, 12), (-20, 6), (16, 22),
)
_CHALK_FONTS = ("Caveat", "Permanent Marker", "Gloria Hallelujah", "Indie Flower")

_MARKET_SHORTCUTS = {
    "Ancient Mariner Lobster Co.": "Ancient Mariner",
    "Pine Tree Seafood & Produce": "Pine Tree",
    "Harbor Fish Market (Lobster)": "Harbor Fish",
    "Harbor Fish Market (Oysters)": "Harbor Fish Oys",
    "Scarborough Fish & Lobster": "Scarborough F&L",
    "Free Range Fish & Lobster": "Free Range",
    "SoPo Seafood Market & Raw Bar": "SoPo Seafood",
    "Two Tides Seafood": "Two Tides",
    "Five Islands Lobster Co.": "Five Islands",
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


def _is_today(ts: str) -> bool:
    dt = _parse_ts(ts)
    if not dt:
        return False
    return dt.astimezone(timezone.utc).date() == datetime.now(timezone.utc).date()


def label_for(key: str) -> str:
    if key in _ITEM_LABELS:
        return _ITEM_LABELS[key]
    return re.sub(r"_+", " ", key).strip().title()


def label_for_row(key: str, snippet: str = "") -> str:
    shell_suffix = ""
    base_key = key
    if key.endswith("_hard_shell"):
        shell_suffix = " Hard"
        base_key = key[: -len("_hard_shell")]
    elif key.endswith("_soft_shell"):
        shell_suffix = " Soft"
        base_key = key[: -len("_soft_shell")]
    label = label_for(base_key)
    if shell_suffix:
        return f"{label}{shell_suffix}"
    if base_key in {"1lb", "1.125lb", "1.25lb", "1.5lb", "1.75lb", "2lb_plus"}:
        snippet_l = snippet.lower()
        if "hard shell" in snippet_l:
            return f"{label} Hard"
        if "soft shell" in snippet_l:
            return f"{label} Soft"
    return label


def short_market(name: str) -> str:
    """Abbreviate long market names for the board."""
    return _MARKET_SHORTCUTS.get(name, name.split("(")[0].strip()[:22])


def market_roster() -> list[dict]:
    """Return every configured market for demo/live board display."""
    return [
        {
            "name": m["name"],
            "short": short_market(m["name"]),
            "location": m.get("location", ""),
            "source": "web + FB" if m.get("web") else "FB",
        }
        for m in MARKETS
    ]


def _demo_market_rows(*, oysters: bool = False) -> list[dict]:
    markets = [
        market for market in market_roster()
        if ("Oysters" in market["name"]) is oysters
    ]
    return [
        {
            "label": market["short"],
            "price_str": "—",
            "price_amount": "—",
            "unit_label": "",
            "market_short": market["source"],
            "confidence": 0,
            "is_unavailable": True,
            "tilt": _TAG_TILTS[i % len(_TAG_TILTS)],
        }
        for i, market in enumerate(markets)
    ]


def format_price(
    price: float,
    unit: str,
    *,
    price_high: float | None = None,
    price_is_range: bool = False,
) -> str:
    if price_is_range and price_high is not None and price_high > price:
        body = f"${price:.2f}–${price_high:.2f}"
    else:
        body = f"${price:.2f}"
    if unit == "ea":
        return f"{body} ea"
    if unit == "doz":
        return f"{body}/doz"
    return f"{body}/lb"


def _range_too_wide_for_board(price: float, price_high: float | None) -> bool:
    """Wide catalog spans are misleading on a glance board."""
    if price_high is None or price_high <= price:
        return False
    return (price_high - price) > 12.0 or price_high > price * 2.2


def price_parts(
    price: float,
    unit: str,
    *,
    price_high: float | None = None,
    price_is_range: bool = False,
    board_glance: bool = False,
) -> tuple[str, str]:
    """Split display price into chalk amount + unit label."""
    if (
        price_is_range
        and price_high is not None
        and price_high > price
    ):
        if board_glance and _range_too_wide_for_board(price, price_high):
            amount = f"from ${price:.2f}"
        else:
            amount = f"${price:.2f}–${price_high:.2f}"
    else:
        amount = f"${price:.2f}"
    if unit == "ea":
        return amount, "ea"
    if unit == "doz":
        return amount, "/doz"
    return amount, "/lb"


def _format_observed(ts: str) -> str:
    dt = _parse_ts(ts)
    if not dt:
        return ts[:16].replace("T", " ") if ts else "—"
    return dt.astimezone().strftime("%b %d · %I:%M %p").replace(" 0", " ").lstrip("0")


def _source_url_lookup() -> dict[tuple[str, str], str]:
    """Map (market, post_id) → source URL from scrape history."""
    lookup: dict[tuple[str, str], str] = {}
    for row in read_jsonl("history.jsonl"):
        market = row.get("market", "")
        pid = row.get("post_id")
        url = row.get("url")
        if market and pid and url:
            lookup[(market, str(pid))] = url
    return lookup


def _market_config_by_name() -> dict[str, dict]:
    return {m["name"]: m for m in MARKETS}


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
    return True


def _is_test_row(row: dict) -> bool:
    """Exclude unit-test fixture rows from the public board."""
    post_id = str(row.get("post_id", ""))
    source_url = str(row.get("source_url") or row.get("url") or "")
    if post_id == "t1" and ("https://x" in source_url or source_url == ""):
        return True
    snippet = (row.get("snippet") or "").strip()
    if snippet == "chicks $5/lb" and row.get("price") == 5.0:
        return True
    if row.get("kind") == "lobster_tier" and row.get("unit") == "lb":
        price = float(row.get("price", 0))
        source = str(row.get("source", ""))
        if price < 6.0 and source not in ("web", "reference", "facebook"):
            return True
    return False


def _display_values_from_row(row: dict) -> tuple[float, str, float | None, bool]:
    """Customer-facing price, unit, optional high, and range flag."""
    display_type = row.get("price_display_type", "")
    display_price = row.get("display_price")
    display_unit = row.get("display_unit")
    display_high = row.get("display_price_high")

    if row.get("kind") == "lobster_tier":
        norm = row.get("normalized_price")
        weight = row.get("normalization_weight") or row.get("normalization_weight_lb")
        raw = row.get("raw_price")
        if norm is None and weight and raw is not None and float(weight) > 0:
            norm = round(float(raw) / float(weight), 2)
        unit = str(row.get("unit", "lb"))
        if norm is not None:
            return float(norm), "lb", None, False
        if unit == "lb" and display_type in ("normalized", "size_specific", "single"):
            price = float(display_price if display_price is not None else row.get("price", 0))
            return price, "lb", None, False
        if raw is not None and weight and float(weight) > 0:
            return round(float(raw) / float(weight), 2), "lb", None, False

    if display_price is not None and display_unit:
        price = float(display_price)
        unit = str(display_unit)
        high = float(display_high) if display_high is not None else None
        is_range = bool(
            row.get("price_is_range")
            or display_type == "range"
            or (high is not None and high > price)
        )
        if is_range and high is None:
            high = row.get("price_high") or row.get("raw_price_high")
            if high is not None:
                high = float(high)
        return price, unit, high, is_range

    price = float(row.get("price", 0))
    unit = str(row.get("unit", "lb"))
    high = row.get("price_high") or row.get("raw_price_high")
    if high is not None:
        high = float(high)
    is_range = bool(
        row.get("price_is_range")
        or display_type == "range"
        or (high is not None and high > price)
    )
    return price, unit, high, is_range


def _provenance_note(row: dict) -> str:
    parts: list[str] = []
    display_type = row.get("price_display_type", "")
    norm = row.get("normalized_price")
    weight = row.get("normalization_weight") or row.get("normalization_weight_lb")
    if display_type in ("normalized", "size_total") and row.get("raw_price") is not None:
        raw = float(row["raw_price"])
        if weight:
            w = float(weight)
            parts.append(f"catalog ${raw:.2f} total ÷ {w:g} lb")
        else:
            parts.append(f"catalog ${raw:.2f} total")
    elif display_type == "size_specific" and row.get("raw_price") is not None:
        parts.append(f"catalog ${float(row['raw_price']):.2f}/lb")
    elif display_type == "normalized" and norm is not None:
        parts.append(f"~${float(norm):.2f}/lb")
    elif weight:
        parts.append(
            f"catalog ${float(row.get('raw_price', 0)):.2f} total "
            f"÷ {float(weight):g} lb"
        )
    elif (
        row.get("price_is_range")
        or row.get("price_display_type") == "range"
    ):
        hi = row.get("display_price_high") or row.get("raw_price_high") or row.get("price_high")
        if hi is not None:
            lo = row.get("display_price") or row.get("raw_price") or row.get("price")
            parts.append(
                f"catalog range ${float(lo):.2f}–${float(hi):.2f}"
            )
    url = row.get("source_url") or ""
    if url:
        parts.append(url)
    return " · ".join(parts)


def _board_market_coverage(
    markets_with_prices: set[str],
    *,
    lobster_board_markets: set[str] | None = None,
    oyster_board_markets: set[str] | None = None,
) -> list[dict]:
    """Board-friendly coverage rows using persisted scrape state."""
    configs = _market_config_by_name()
    on_lobster_board = lobster_board_markets or set()
    on_oyster_board = oyster_board_markets or set()
    on_board = on_lobster_board | on_oyster_board
    persisted = read_json("market-coverage.json")
    if persisted and persisted.get("markets"):
        out: list[dict] = []
        for entry in persisted["markets"]:
            name = entry.get("name", "")
            cfg = configs.get(name, {})
            status = entry.get("status", "blocked")
            blocker = entry.get("blocker") or ""
            if name in on_board:
                status = "live"
                blocker = ""
            elif name in markets_with_prices or int(entry.get("passed_rows", 0)) > 0:
                status = "partial"
                blocker = (
                    "lobster_not_board_ready"
                    if name not in on_lobster_board
                    else "fetched_but_no_passed_rows"
                )
            out.append({
                "name": name,
                "short": short_market(name),
                "location": cfg.get("location", ""),
                "status": status,
                "reason": human_blocker_reason(blocker),
                "fetched": int(entry.get("posts_fetched", 0)),
                "source_hint": entry.get("source_used") or (
                    "web + FB" if cfg.get("web") else "FB"
                ),
                "web_url": cfg.get("web") or cfg.get("reference_url") or "",
            })
        return out

    logs = read_jsonl("run-log.jsonl")
    latest = logs[-1] if logs else {}
    fetch_map = {
        e.get("market", ""): int(e.get("fetched", 0))
        for e in latest.get("errors", [])
    }
    out = []
    for m in MARKETS:
        name = m["name"]
        fetched = fetch_map.get(name, 0)
        has_prices = name in markets_with_prices
        if has_prices:
            status = "live"
            reason = ""
        elif fetched > 0:
            status = "partial"
            reason = human_blocker_reason("fetched_but_no_passed_rows")
        else:
            status = "blocked"
            if m.get("web"):
                reason = "Web + FB unreachable — check network or auth"
            elif m.get("reference_url"):
                reason = "FB blocked — menu reference only, no live scrape"
            else:
                reason = "FB only — needs cookies or search credentials"
        out.append({
            "name": name,
            "short": short_market(name),
            "location": m.get("location", ""),
            "status": status,
            "reason": reason,
            "fetched": fetched,
            "source_hint": "web + FB" if m.get("web") else "FB",
            "web_url": m.get("web") or m.get("reference_url") or "",
        })
    return out


def _row_identity(row: dict) -> tuple:
    kind = row.get("kind", "")
    if kind == "special":
        title = (
            row.get("catalog_title")
            or row.get("snippet")
            or row.get("key", "")
        )
        return (
            row.get("market", ""),
            kind,
            row.get("key", ""),
            str(title).strip().lower()[:80],
        )
    base = (
        row.get("market", ""),
        kind,
        row.get("key", ""),
    )
    # FB posts emit many lobster_tier rows per size under the same key — keep each price.
    if kind == "lobster_tier":
        return base + (float(row.get("price", 0)),)
    return base


def _display_values(row: dict) -> tuple[float, str, float | None, bool]:
    """Resolve board-facing price, unit, optional high, and range flag."""
    unit = row.get("display_unit") or row.get("unit", "lb")
    price = row.get("display_price")
    if price is None:
        price = row.get("price", 0)
    price = float(price)

    price_high = row.get("display_price_high")
    if price_high is None:
        price_high = row.get("price_high")
    if price_high is None:
        price_high = row.get("raw_price_high")
    if price_high is not None:
        price_high = float(price_high)

    price_is_range = bool(
        row.get("price_is_range")
        or row.get("price_display_type") == "range"
    )
    if price_high is not None and price_high > price:
        price_is_range = True
    return price, unit, price_high, price_is_range


def _lobster_board_sort_key(item: dict) -> tuple:
    """Headline rows: lowest price first, then market name."""
    return (item.get("sort_price", item.get("price", 0)), item.get("market_short", ""))


def _shell_from_key(key: str) -> str | None:
    if key.endswith("_soft_shell") or key == "soft_shell":
        return "soft"
    if key.endswith("_hard_shell") or key in ("hard_shell", "old_shell", "select"):
        return "hard"
    if key in ("chicks", "1lb", "1.125lb", "1.25lb", "1.5lb", "1.75lb", "2lb_plus"):
        return "hard"
    return None


_LOBSTER_HEADLINE_TIER_RANK: dict[str, int] = {
    "chicks_soft_shell": 0,
    "chicks_hard_shell": 0,
    "1lb_soft_shell": 1,
    "1lb_hard_shell": 1,
    "1.125lb": 2,
    "soft_shell": 3,
    "hard_shell": 3,
    "1.25lb_soft_shell": 10,
    "1.25lb_hard_shell": 10,
    "1.5lb_soft_shell": 11,
    "1.5lb_hard_shell": 11,
    "1.75lb_soft_shell": 12,
    "1.75lb_hard_shell": 12,
    "2lb_plus_soft_shell": 13,
    "2lb_plus_hard_shell": 13,
    "2lb_plus": 14,
    "select": 15,
}

_LOBSTER_SNIPPET_REJECT = (
    "steamer", "steamers", "culls", "cull ", "cull:", "butter", "chowder", "bisque",
    "scallop", "shrimp", "mussel", "clam", "crab", "snow crab",
    "lob/crab", "clear meat", "harborfish.com", "tuna", "haddock",
    "salmon", "cod ", "swordfish", "halibut", "sole", "flounder",
)


def _is_lobster_contaminated_snippet(snippet: str) -> bool:
    text = snippet.lower()
    if "lobster" in text:
        return False
    return any(token in text for token in _LOBSTER_SNIPPET_REJECT)


def _is_valid_headline_tier(item: dict) -> bool:
    """Drop mis-parsed steamers, culls, and other species from lobster headlines."""
    price = float(item.get("sort_price", item.get("price", 0)))
    if price <= 5.0 or price > 28.0:
        return False
    snippet = str(item.get("snippet", ""))
    if _is_lobster_contaminated_snippet(snippet):
        return False
    return True


def _headline_tier_sort_key(item: dict) -> tuple:
    """Prefer entry-size tiers (chix / 1 lb) over bare aggregates and upsells."""
    key = item.get("key", "")
    rank = _LOBSTER_HEADLINE_TIER_RANK.get(key, 20)
    return (rank, float(item.get("sort_price", item.get("price", 0))))


def _tier_short_label(key: str) -> str:
    base = key
    for suffix in ("_soft_shell", "_hard_shell"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            break
    short = {
        "chicks": "chix",
        "1lb": "1 lb",
        "1.25lb": "1¼ lb",
        "1.5lb": "1½ lb",
        "1.75lb": "1¾ lb",
        "2lb_plus": "2 lb+",
    }
    return short.get(base, label_for(base))


def _best_headline_tier(tier_items: list[dict]) -> dict | None:
    """Pick the lowest entry-size trustworthy tier for a shell group."""
    tier_items.sort(key=_headline_tier_sort_key)
    for item in tier_items:
        if _is_valid_headline_tier(item):
            return item
    return None


def _collapse_lobster_headlines(items: list[dict]) -> list[dict]:
    """One scannable row per market — entry soft/hard $/lb when trustworthy."""
    groups: dict[tuple[str, str], list[dict]] = {}
    for item in items:
        shell = _shell_from_key(item.get("key", ""))
        if not shell:
            continue
        groups.setdefault((item.get("market", ""), shell), []).append(item)

    by_market: dict[str, dict[str, dict]] = {}
    for (market, shell), tier_items in groups.items():
        chosen = _best_headline_tier(tier_items)
        if chosen:
            by_market.setdefault(market, {})[shell] = chosen

    market_order = [m["name"] for m in MARKETS if m["name"] in by_market]
    for name in by_market:
        if name not in market_order:
            market_order.append(name)

    headlines: list[dict] = []
    for market in market_order:
        shells = by_market[market]
        soft = shells.get("soft")
        hard = shells.get("hard")
        if not soft and not hard:
            continue
        if soft and hard:
            anchor = soft
            soft_price = float(soft.get("sort_price", soft.get("price", 0)))
            hard_price = float(hard.get("sort_price", hard.get("price", 0)))
            detail = f"soft ${soft_price:.2f} · hard ${hard_price:.2f}"
            sort_price = min(soft_price, hard_price)
            lo, hi = sorted([soft_price, hard_price])
            price_amount = f"${lo:.2f}–${hi:.2f}" if lo != hi else f"${lo:.2f}"
        elif soft:
            anchor = soft
            sort_price = float(soft.get("sort_price", soft.get("price", 0)))
            tier = _tier_short_label(anchor.get("key", ""))
            detail = (
                f"{tier} · soft ${sort_price:.2f}"
                if tier not in ("Soft Shell", "Hard Shell", "Lobster")
                else f"soft ${sort_price:.2f}"
            )
            price_amount = f"${sort_price:.2f}"
        else:
            anchor = hard
            sort_price = float(hard.get("sort_price", hard.get("price", 0)))
            tier = _tier_short_label(anchor.get("key", ""))
            detail = (
                f"{tier} · hard ${sort_price:.2f}"
                if tier not in ("Soft Shell", "Hard Shell", "Lobster")
                else f"hard ${sort_price:.2f}"
            )
            price_amount = f"${sort_price:.2f}"
        headlines.append({
            **anchor,
            "label": "Lobster",
            "row_primary": short_market(market),
            "row_secondary": detail,
            "subtext": "",
            "sort_price": sort_price,
            "price_amount": price_amount,
            "unit_label": "/lb",
            "price_str": f"${sort_price:.2f}/lb",
            "is_headline": True,
            "is_consolidated": True,
        })

    headlines.sort(key=lambda x: (x.get("sort_price", 0), x.get("market_short", "")))

    configs = _market_config_by_name()
    by_short: dict[str, dict] = {}
    for headline in headlines:
        short = headline["row_primary"]
        prev = by_short.get(short)
        if prev is None:
            by_short[short] = headline
            continue
        prev_web = configs.get(prev.get("market", ""), {}).get("web")
        cur_web = configs.get(headline.get("market", ""), {}).get("web")
        if cur_web and not prev_web:
            by_short[short] = headline
        elif headline.get("source") == "web" and prev.get("source") != "web":
            by_short[short] = headline

    deduped = list(by_short.values())
    deduped.sort(key=lambda x: (x.get("sort_price", 0), x.get("market_short", "")))
    return deduped[:_MAX_LOBSTER_HEADLINES]


_MAX_SECTION_ITEMS = 4
_MAX_LOBSTER_HEADLINES = 9
_MAX_SPECIALS_PER_MARKET = 2
_MAX_SPECIALS_TOTAL = 8

_BLOCKER_LABELS: dict[str, str] = {
    "no_posts_from_facebook": "Facebook feed unavailable",
    "no_facebook_cookies": "Facebook cookies needed",
    "facebook_auth_failed": "Facebook login needed",
    "facebook_blocked": "Facebook blocked",
    "ddg_captcha": "Search blocked (captcha)",
    "network_error": "Network unreachable",
    "no_web_prices": "Website had no gated prices",
    "web_fetch_failed": "Website unavailable",
    "web_fetch_failed_or_empty_catalog": "Website unavailable",
    "no_posts_from_configured_sources": "No price source reachable",
    "fetched_but_no_passed_rows": "Fetched but no prices passed quality gate",
    "lobster_not_board_ready": "Lobster prices not board-ready yet",
    "no_board_ready_prices": "No prices passed quality gate",
}


def human_blocker_reason(code: str) -> str:
    """Turn scrape blocker codes into board-friendly copy."""
    if not code:
        return "Unavailable"
    if code in _BLOCKER_LABELS:
        return _BLOCKER_LABELS[code]
    if code.startswith("facebook_scrape_failed:"):
        return "Facebook scrape failed"
    if code.startswith("no_public_price_source:"):
        return "No public price feed found"
    if "reference_menu:" in code:
        return "Menu reference only — no live scrape"
    return code.replace("_", " ")


def _special_item_rank(item: dict) -> tuple:
    key = item.get("key", "")
    iconic = key in ("lobster_roll", "chowder", "bisque")
    return (
        0 if iconic else 1,
        1 if item.get("price_is_range") else 0,
        -int(item.get("confidence", 0)),
        item.get("sort_price", item.get("price", 0)),
    )


def _cap_specials_by_market(items: list[dict]) -> list[dict]:
    """Keep up to N specials per market, max total — preserve every market with data."""
    if not items:
        return []
    by_market: dict[str, list[dict]] = {}
    for item in items:
        by_market.setdefault(item.get("market", ""), []).append(item)
    for market_items in by_market.values():
        market_items.sort(key=_special_item_rank)

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
            market_order.index(x.get("market", ""))
            if x.get("market", "") in market_order
            else 99,
            _special_item_rank(x),
        ),
    )
    return capped


def _is_stale_lobster_key(key: str, market: str, lobster_keys: set[str]) -> bool:
    """Drop legacy aggregate keys only when a shell-qualified variant of the same tier exists."""
    if "_hard_shell" in key or "_soft_shell" in key:
        return False
    legacy = {"hard_shell", "soft_shell", "chicks", "1lb", "1.25lb", "1.5lb", "1.75lb", "2lb_plus"}
    if key not in legacy:
        return False
    for suffix in ("_hard_shell", "_soft_shell"):
        if f"{key}{suffix}" in lobster_keys:
            return True
    if key in {"chicks", "1lb", "1.25lb", "1.5lb", "1.75lb", "2lb_plus"}:
        return any(
            k.startswith(f"{key}_") and (k.endswith("_hard_shell") or k.endswith("_soft_shell"))
            for k in lobster_keys
        )
    return False


def _prefer_lobster_tier_row(prev: dict, new: dict) -> bool:
    """When deduping lobster tiers, prefer newer observations; tie-break to entry $/lb."""
    prev_ts = prev.get("observed_at", "")
    new_ts = new.get("observed_at", "")
    if new_ts > prev_ts:
        return True
    if new_ts < prev_ts:
        return False
    return float(new.get("price", 0)) < float(prev.get("price", 0))


def load_board_rows(
    *,
    min_confidence: int = 70,
    today_only: bool = False,
    market: str | None = None,
) -> list[dict]:
    rows = read_jsonl("prices.jsonl")
    filtered: list[dict] = []
    for r in rows:
        if r.get("gate_passed") is False:
            continue
        if _is_test_row(r):
            continue
        if r.get("kind") == "special" and not _is_clean_special_row(r):
            continue
        conf = int(r.get("confidence", 0))
        if conf < min_confidence and r.get("gate_passed") is not True:
            continue
        if r.get("reject_reason") and r.get("gate_passed") is not True:
            continue
        if market and market.lower() not in r.get("market", "").lower():
            continue
        observed = r.get("observed_at", "")
        if today_only and not _is_today(observed):
            continue
        filtered.append(r)

    # Latest observation wins per market + kind + key; lobster tiers tie-break to entry $/lb.
    latest: dict[tuple, dict] = {}
    for r in filtered:
        dedupe = _row_identity(r)
        prev = latest.get(dedupe)
        if prev is None:
            latest[dedupe] = r
        elif r.get("kind") == "lobster_tier":
            if _prefer_lobster_tier_row(prev, r):
                latest[dedupe] = r
        elif r.get("observed_at", "") >= prev.get("observed_at", ""):
            latest[dedupe] = r
    rows_out = list(latest.values())

    lobster_keys_by_market: dict[str, set[str]] = {}
    for r in rows_out:
        if r.get("kind") == "lobster_tier":
            lobster_keys_by_market.setdefault(r.get("market", ""), set()).add(r.get("key", ""))

    final: list[dict] = []
    for r in rows_out:
        if r.get("kind") == "lobster_tier":
            market_name = r.get("market", "")
            keys = lobster_keys_by_market.get(market_name, set())
            if _is_stale_lobster_key(r.get("key", ""), market_name, keys):
                continue
        final.append(r)

    configs = _market_config_by_name()
    web_lobster_markets: set[str] = set()
    for r in final:
        if r.get("kind") != "lobster_tier" or r.get("source") != "web":
            continue
        if configs.get(r.get("market", ""), {}).get("web"):
            web_lobster_markets.add(r.get("market", ""))
    if web_lobster_markets:
        final = [
            r for r in final
            if not (
                r.get("kind") == "lobster_tier"
                and r.get("market") in web_lobster_markets
                and r.get("source") != "web"
            )
        ]
    return final


def _calculate_historical_trends() -> dict:
    from collections import defaultdict
    by_date_shell = defaultdict(lambda: defaultdict(list))
    for r in read_jsonl("prices.jsonl"):
        if r.get("kind") != "lobster_tier" or r.get("gate_passed") is False:
            continue
        ts = r.get("observed_at", "")
        if not ts:
            continue
        date_str = ts[:10]
        key = r.get("key", "").lower()
        snippet = r.get("snippet", "").lower()
        
        is_soft = "soft" in key or "soft" in snippet
        is_hard = "hard" in key or "hard" in snippet or any(k in key for k in ("chicks", "1lb", "1.25lb", "1.5lb", "1.75lb", "2lb"))
        
        price = float(r.get("price", 0))
        if not (5.0 < price < 50.0):
            continue
            
        if is_soft:
            by_date_shell[date_str]["soft"].append(price)
        elif is_hard:
            by_date_shell[date_str]["hard"].append(price)
            
    dates = sorted(by_date_shell.keys())[-14:]
    labels = []
    soft_avgs = []
    hard_avgs = []
    
    for d in dates:
        try:
            dt = datetime.strptime(d, "%Y-%m-%d")
            labels.append(dt.strftime("%b %d"))
        except ValueError:
            labels.append(d[5:])
            
        soft_list = by_date_shell[d]["soft"]
        hard_list = by_date_shell[d]["hard"]
        soft_avgs.append(round(sum(soft_list) / len(soft_list), 2) if soft_list else None)
        hard_avgs.append(round(sum(hard_list) / len(hard_list), 2) if hard_list else None)
        
    return {
        "labels": labels,
        "soft_shell": soft_avgs,
        "hard_shell": hard_avgs,
    }


def build_board(
    *,
    min_confidence: int = 70,
    today_only: bool = False,
    market: str | None = None,
) -> dict:
    """Group gated prices into board sections."""
    rows = load_board_rows(
        min_confidence=min_confidence, today_only=today_only, market=market,
    )
    url_lookup = _source_url_lookup()
    sections: dict[str, list[dict]] = {
        "lobster": [],
        "oyster": [],
        "special": [],
    }
    latest_ts = ""
    seen_items: set[tuple] = set()
    markets_with_prices: set[str] = set()
    tag_index = 0
    for r in rows:
        kind = r.get("kind", "")
        market_name = r.get("market", "?")
        if kind == "lobster_tier":
            bucket = "lobster"
            # Oysters-only market row — skip unless explicitly configured with lobster web URL.
            if market_name == "Harbor Fish Market (Oysters)":
                continue
        elif kind == "oyster_tier":
            bucket = "oyster"
        elif kind == "special":
            bucket = "special"
        else:
            continue
        label = label_for_row(r.get("key", "?"), r.get("snippet", ""))
        display_price, display_unit, display_high, price_is_range = _display_values_from_row(r)
        if kind == "special":
            title = (
                r.get("catalog_title")
                or r.get("snippet")
                or label
            )
            dedupe_key = (
                market_name,
                kind,
                r.get("key", ""),
                str(title).strip().lower()[:80],
            )
        else:
            dedupe_key = (
                market_name,
                kind,
                r.get("key", ""),
                r.get("shell_tier", ""),
            )
        if dedupe_key in seen_items:
            continue
        seen_items.add(dedupe_key)
        markets_with_prices.add(market_name)
        post_id = r.get("post_id", "")
        amount, unit_label = price_parts(
            display_price, display_unit,
            price_high=display_high, price_is_range=price_is_range,
            board_glance=bucket == "special",
        )
        provenance = _provenance_note(r)
        special_label = label
        if bucket == "special":
            title = r.get("catalog_title") or r.get("snippet") or label
            special_label = str(title).split("(")[0].strip()
            if special_label.lower().startswith("fresh "):
                special_label = special_label[6:].strip()
        item = {
            "label": label,
            "row_primary": (
                f"{short_market(market_name)} — {special_label}"
                if bucket == "special"
                else label
            ),
            "key": r.get("key", ""),
            "price": float(r.get("price", 0)),
            "sort_price": display_price,
            "price_high": display_high,
            "price_is_range": price_is_range,
            "unit": display_unit,
            "price_str": format_price(
                display_price, display_unit,
                price_high=display_high, price_is_range=price_is_range,
            ),
            "price_amount": amount,
            "unit_label": unit_label,
            "market": market_name,
            "market_short": short_market(market_name),
            "subtext": "",
            "confidence": int(r.get("confidence", 0)),
            "observed_at": r.get("observed_at", ""),
            "observed_display": _format_observed(r.get("observed_at", "")),
            "source": r.get("source", "unknown"),
            "source_url": r.get("source_url") or url_lookup.get(
                (market_name, str(post_id)), "",
            ),
            "post_id": post_id,
            "snippet": r.get("snippet", ""),
            "provenance": provenance,
            "raw_price": r.get("raw_price"),
            "normalized_price": r.get("normalized_price"),
            "normalization_weight": r.get("normalization_weight") or r.get("normalization_weight_lb"),
            "tilt": _TAG_TILTS[tag_index % len(_TAG_TILTS)],
        }
        tag_index += 1
        sections[bucket].append(item)
        if r.get("observed_at", "") > latest_ts:
            latest_ts = r.get("observed_at", "")

    sections["lobster"] = _collapse_lobster_headlines(sections["lobster"])
    lobster_board_markets = {item.get("market", "") for item in sections["lobster"]}
    sections["oyster"].sort(key=lambda x: (x.get("sort_price", x["price"]), x["market_short"]))
    sections["oyster"] = sections["oyster"][:_MAX_SECTION_ITEMS]
    oyster_board_markets = {item.get("market", "") for item in sections["oyster"]}
    sections["special"] = _cap_specials_by_market(sections["special"])

    now = datetime.now(timezone.utc)
    coverage = _board_market_coverage(
        markets_with_prices,
        lobster_board_markets=lobster_board_markets,
        oyster_board_markets=oyster_board_markets,
    )
    live_count = sum(1 for c in coverage if c["status"] == "live")
    partial_count = sum(1 for c in coverage if c["status"] == "partial")
    blocked_count = sum(1 for c in coverage if c["status"] == "blocked")
    unavailable_count = blocked_count + partial_count
    live_names = [c["short"] for c in coverage if c["status"] == "live"]
    if live_names and unavailable_count:
        coverage_summary = (
            f"{len(live_names)} live · {unavailable_count} awaiting feed"
        )
    elif live_names:
        coverage_summary = f"{len(live_names)} live"
    elif unavailable_count:
        coverage_summary = f"{unavailable_count} markets awaiting feed"
    else:
        coverage_summary = "No live prices yet"
    return {
        "title": "MAINE COAST SEAFOOD BOARD",
        "subtitle": "Gorham base · Maine coast watchlist",
        "updated_at": latest_ts or now.isoformat(),
        "display_date": now.astimezone().strftime("%A, %B %-d").replace(" 0", " "),
        "sections": sections,
        "monitored_markets": market_roster(),
        "market_coverage": coverage,
        "live_market_count": live_count,
        "blocked_market_count": blocked_count,
        "partial_market_count": partial_count,
        "coverage_summary": coverage_summary,
        "live_market_names": live_names,
        "total_items": sum(len(v) for v in sections.values()),
        "trends": _calculate_historical_trends(),
    }


def _demo_board() -> dict:
    """Sample board when no prices.jsonl exists yet."""
    now = datetime.now(timezone.utc).isoformat()
    coverage = _board_market_coverage(set())
    return {
        "title": "MAINE COAST SEAFOOD BOARD",
        "subtitle": "Gorham base · Maine coast watchlist",
        "updated_at": now,
        "display_date": datetime.now(timezone.utc).strftime("%A, %B %d"),
        "sections": {
            "lobster": _demo_market_rows(),
            "oyster": _demo_market_rows(oysters=True),
            "special": [],
        },
        "monitored_markets": market_roster(),
        "market_coverage": coverage,
        "total_items": 0,
        "is_demo": True,
        "trends": {
            "labels": ["Jul 1", "Jul 2", "Jul 3", "Jul 4", "Jul 5"],
            "soft_shell": [12.99, 13.25, 12.50, 13.00, 13.50],
            "hard_shell": [14.99, 14.50, 14.25, 14.99, 14.75],
        },
    }


def get_board(*, demo: bool = False, **kwargs) -> dict:
    if demo:
        return _demo_board()
    board = build_board(**kwargs)
    board["is_demo"] = False
    return board


# ---- Terminal (ANSI chalkboard) ----

ANSI = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[2m",
    "bg": "\033[48;5;236m",
    "chalk": "\033[38;5;252m",
    "lobster": "\033[38;5;203m",
    "ocean": "\033[38;5;39m",
    "gold": "\033[38;5;220m",
    "rope": "\033[38;5;130m",
}


def _wrap_market_names(markets: list[dict], *, width: int) -> list[str]:
    names = [m["short"] for m in markets]
    lines: list[str] = []
    current = "  "
    for name in names:
        part = name if not current.strip() else f" · {name}"
        if len(current) + len(part) > width and current.strip():
            lines.append(current)
            current = f"  {name}"
        else:
            current += part
    if current.strip():
        lines.append(current)
    return lines


def render_terminal(board: dict, *, width: int = 62) -> str:
    a = ANSI
    lines: list[str] = []
    w = width

    def bar(char: str = "─") -> str:
        return f"{a['rope']}{char * (w - 2)}{a['reset']}"

    lines.append(f"{a['bg']}{a['rope']}╔{'═' * (w - 2)}╗{a['reset']}")
    title = board["title"].center(w - 2)
    lines.append(f"{a['bg']}{a['rope']}║{a['reset']}{a['bg']}{a['bold']}{a['chalk']}{title}{a['reset']}{a['bg']}{a['rope']}║{a['reset']}")
    sub = board["subtitle"].center(w - 2)
    lines.append(f"{a['bg']}{a['rope']}║{a['reset']}{a['bg']}{a['dim']}{a['chalk']}{sub}{a['reset']}{a['bg']}{a['rope']}║{a['reset']}")
    date_line = board.get("display_date", "").center(w - 2)
    lines.append(f"{a['bg']}{a['rope']}║{a['reset']}{a['bg']}{a['gold']}{date_line}{a['reset']}{a['bg']}{a['rope']}║{a['reset']}")
    lines.append(f"{a['bg']}{a['rope']}╠{'═' * (w - 2)}╣{a['reset']}")

    for section_key in ("lobster", "oyster", "special"):
        emoji, heading, _u = _SECTION_META[section_key]
        items = board["sections"].get(section_key, [])
        accent = a["lobster"] if section_key == "lobster" else a["ocean"] if section_key == "oyster" else a["gold"]
        head = f" {emoji}  {heading} "
        pad = w - 2 - len(head)
        lines.append(f"{a['bg']}{a['rope']}║{a['reset']}{a['bg']}{accent}{a['bold']}{head}{' ' * max(0, pad)}{a['reset']}{a['bg']}{a['rope']}║{a['reset']}")
        if not items:
            empty = "  (nothing on the board yet)".ljust(w - 2)[: w - 2]
            lines.append(f"{a['bg']}{a['rope']}║{a['reset']}{a['bg']}{a['dim']}{a['chalk']}{empty}{a['reset']}{a['bg']}{a['rope']}║{a['reset']}")
        else:
            cap = 8 if section_key == "lobster" else (
                _MAX_SPECIALS_TOTAL if section_key == "special" else _MAX_SECTION_ITEMS
            )
            for item in items[:cap]:
                if section_key == "special":
                    left = item.get("row_primary") or f"{item['market_short']} — {item['label']}"
                else:
                    left = f"{item['market_short']} · {item['label']}"
                visible = f"  {left:<28} {item['price_str']:>14}"[: w - 2]
                visible = visible.ljust(w - 2)
                lines.append(
                    f"{a['bg']}{a['rope']}║{a['reset']}{a['bg']}{a['chalk']}{visible}{a['reset']}{a['bg']}{a['rope']}║{a['reset']}"
                )
        sep = f"{a['rope']}{'·' * (w - 2)}{a['reset']}"
        lines.append(f"{a['bg']}{a['rope']}║{a['reset']}{a['bg']}{sep}{a['bg']}{a['rope']}║{a['reset']}")

    cov = board.get("coverage_summary", "")
    if board.get("is_demo"):
        demo_note = "  DEMO BOARD — run scrape for live prices"
    elif cov:
        demo_note = f"  {cov} · updated today"
    else:
        demo_note = f"  {board['total_items']} prices · AAA-gated"
    demo_note = demo_note.center(w - 2)[: w - 2]
    lines.append(f"{a['bg']}{a['rope']}║{a['reset']}{a['bg']}{a['dim']}{a['chalk']}{demo_note}{a['reset']}{a['bg']}{a['rope']}║{a['reset']}")
    lines.append(f"{a['bg']}{a['rope']}╚{'═' * (w - 2)}╝{a['reset']}")
    return "\n".join(lines)




def render_html(board: dict) -> str:
    from chalk_board_html import render_chalk_html
    return render_chalk_html(board)


def write_html_board(path: Path | None = None, **kwargs) -> Path:
    board = get_board(**kwargs)
    out = path or (DATA_DIR / "board.html")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_html(board), encoding="utf-8")
    return out


# ---- Telegram board formatting ----

def render_telegram_board(
    market: str,
    items: list[dict],
    *,
    heading: str = "TODAY'S CATCH",
    emoji: str = "🐟",
) -> str:
    """Chalkboard-style monospace block for Telegram."""
    lines = [f"{emoji} *{heading}* — {market}", "```"]
    lines.append("╔════════════════════════════╗")
    lines.append(f"║  {heading[:24].ljust(24)}  ║")
    lines.append("╠════════════════════════════╣")
    for item in items[:8]:
        label = label_for(item.get("key", item.get("label", "?")))[:14]
        price = item.get("price_str") or format_price(
            float(item.get("price", 0)), item.get("unit", "lb"),
        )
        row = f"  {label:<14} {price:>10}"
        lines.append(f"║{row:<28}║")
    lines.append("╚════════════════════════════╝")
    lines.append("```")
    return "\n".join(lines)
