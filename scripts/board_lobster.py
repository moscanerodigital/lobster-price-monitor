"""Lobster headline consolidation and cull/snippet filtering for board rendering."""

from __future__ import annotations

import re

from market_names import short_market
from markets import MARKETS

_MAX_LOBSTER_HEADLINES = 9

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
    "steamer",
    "steamers",
    "culls",
    "cull ",
    "cull:",
    "butter",
    "chowder",
    "bisque",
    "scallop",
    "shrimp",
    "mussel",
    "clam",
    "crab",
    "snow crab",
    "lob/crab",
    "clear meat",
    "harborfish.com",
    "tuna",
    "haddock",
    "salmon",
    "cod ",
    "swordfish",
    "halibut",
    "sole",
    "flounder",
)

_LOBSTER_TIER_SIGNAL = re.compile(
    r"\b(?:soft[\s-]?shell|hard[\s-]?shell|chix|chicks|select|1\s*lb|1\.125|1\.25|1\.5|1\.75|2\s*lb)\b",
    re.I,
)


def _shell_from_key(key: str, snippet: str = "") -> str | None:
    if key.endswith("_soft_shell") or key == "soft_shell":
        return "soft"
    if key.endswith("_hard_shell") or key in ("hard_shell", "old_shell", "select"):
        return "hard"
    snippet_l = snippet.lower()
    if key in ("chicks", "1lb", "1.125lb", "1.25lb", "1.5lb", "1.75lb", "2lb_plus"):
        if "soft shell" in snippet_l or "soft-shell" in snippet_l:
            return "soft"
        if "hard shell" in snippet_l or "hard-shell" in snippet_l:
            return "hard"
        return None
    return None


def _has_lobster_tier_signal(text: str) -> bool:
    return bool(_LOBSTER_TIER_SIGNAL.search(text))


def _is_lobster_contaminated_snippet(snippet: str) -> bool:
    text = snippet.lower()
    if "lobster" in text:
        return False
    reject_tokens = _LOBSTER_SNIPPET_REJECT
    if _has_lobster_tier_signal(text):
        reject_tokens = tuple(token for token in _LOBSTER_SNIPPET_REJECT if "cull" not in token)
    return any(token in text for token in reject_tokens)


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
    base = key
    for suffix in ("_soft_shell", "_hard_shell"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            break
    rank = _LOBSTER_HEADLINE_TIER_RANK.get(key, _LOBSTER_HEADLINE_TIER_RANK.get(base, 20))
    return (rank, float(item.get("sort_price", item.get("price", 0))))


def _tier_short_label(key: str) -> str:
    from board_render import label_for

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
    from board_render import _market_config_by_name

    groups: dict[tuple[str, str], list[dict]] = {}
    for item in items:
        shell = _shell_from_key(item.get("key", ""), item.get("snippet", ""))
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
        headlines.append(
            {
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
            }
        )

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
