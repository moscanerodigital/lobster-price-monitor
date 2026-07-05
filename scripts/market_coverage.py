"""Market coverage status — per-market passed/blocked tracking for AAA gate."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

from markets import MARKETS

StatusKind = Literal["passed", "blocked"]


@dataclass
class MarketStatus:
    market: str
    status: StatusKind
    source: str | None = None
    rows_passed: int = 0
    blocker_reason: str | None = None
    source_url: str | None = None
    fetched_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
    )

    def as_dict(self) -> dict:
        out: dict = {
            "market": self.market,
            "status": self.status,
            "fetched_at": self.fetched_at,
        }
        if self.source:
            out["source"] = self.source
        if self.rows_passed:
            out["rows_passed"] = self.rows_passed
        if self.blocker_reason:
            out["blocker_reason"] = self.blocker_reason
        if self.source_url:
            out["source_url"] = self.source_url
        return out


def _short_market(name: str) -> str:
    shortcuts = {
        "Ancient Mariner Lobster Co.": "Ancient Mariner",
        "Pine Tree Seafood & Produce": "Pine Tree",
        "Harbor Fish Market (Lobster)": "Harbor Fish Lobster",
        "Harbor Fish Market (Oysters)": "Harbor Fish Oysters",
        "Scarborough Fish & Lobster": "Scarborough F&L",
        "Free Range Fish & Lobster": "Free Range",
        "SoPo Seafood Market & Raw Bar": "SoPo Seafood",
        "Two Tides Seafood": "Two Tides",
        "Five Islands Lobster Co.": "Five Islands",
    }
    return shortcuts.get(name, name.split("(")[0].strip()[:22])


def _blocker_for_zero_fetch(market: dict, *, fb_error: str | None, had_cookies: bool) -> str:
    if market.get("web"):
        return "web_fetch_failed"
    if not had_cookies:
        return "no_facebook_cookies"
    if fb_error:
        return f"facebook_scrape_failed:{fb_error}"
    return "no_public_price_source:ddg_captcha_or_no_results"


def build_market_status(
    market: dict,
    *,
    posts: list[dict],
    rows_passed: int,
    fb_error: str | None = None,
    had_cookies: bool = False,
) -> MarketStatus:
    """Derive coverage status from scrape results for one market."""
    if rows_passed > 0:
        web_post = next((p for p in posts if p.get("source") == "web"), None)
        fb_post = next((p for p in posts if p.get("source") != "web"), None)
        source = (web_post or fb_post or {}).get("source", "unknown")
        return MarketStatus(
            market=market["name"],
            status="passed",
            source=source,
            rows_passed=rows_passed,
            source_url=(web_post or fb_post or {}).get("url"),
        )
    reason = _blocker_for_zero_fetch(market, fb_error=fb_error, had_cookies=had_cookies)
    ref = market.get("reference_url")
    if ref and not market.get("web"):
        reason = f"{reason};reference_menu:{ref}"
    return MarketStatus(
        market=market["name"],
        status="blocked",
        blocker_reason=reason,
        source_url=market.get("web") or market.get("reference_url"),
    )


def all_markets_accounted(statuses: list[MarketStatus]) -> bool:
    names = {s.market for s in statuses}
    return len(names) == len(MARKETS) and all(m["name"] in names for m in MARKETS)


def build_market_coverage() -> list[dict]:
    """Board/AAA coverage row for every configured market."""
    from state import latest_run_log, read_json, read_jsonl

    run = latest_run_log() or {}
    file_cov = read_json("market-coverage.json") or {}
    run_by_name: dict[str, dict] = {}
    for e in run.get("market_coverage", []) + run.get("market_status", []):
        key = e.get("name") or e.get("market", "")
        if key:
            run_by_name[key] = e
    file_by_name: dict[str, dict] = {}
    for e in file_cov.get("markets", []):
        key = e.get("name") or e.get("market", "")
        if key:
            file_by_name[key] = e
    err_by_name = {e.get("market", ""): e for e in run.get("errors", [])}
    passed_counts = Counter(
        r.get("market", "")
        for r in read_jsonl("prices.jsonl")
        if r.get("gate_passed", True)
    )

    rows: list[dict] = []
    for market in MARKETS:
        name = market["name"]
        rc = run_by_name.get(name, {})
        fc = file_by_name.get(name, {})
        err = err_by_name.get(name, {})
        passed_rows = int(
            rc.get("cumulative_passed_rows")
            or rc.get("passed_rows")
            or fc.get("cumulative_passed_rows")
            or fc.get("passed_rows")
            or passed_counts.get(name, 0)
        )
        posts_fetched = int(rc.get("posts_fetched") or err.get("fetched") or 0)
        blocker = rc.get("blocker") or err.get("blocker") or fc.get("blocker")

        if passed_rows > 0:
            status = "live"
            reason = ""
        elif posts_fetched > 0:
            status = "partial"
            from board_render import human_blocker_reason
            reason = human_blocker_reason("fetched_but_no_passed_rows")
        else:
            status = "blocked"
            if blocker:
                from board_render import human_blocker_reason
                reason = human_blocker_reason(str(blocker))
            elif market.get("web"):
                reason = "Web + FB unreachable — check network or auth"
            elif market.get("reference_url"):
                reason = "FB blocked — menu reference only, no live scrape"
            else:
                reason = "FB only — needs cookies or search credentials"

        rows.append({
            "name": name,
            "short": _short_market(name),
            "location": market.get("location", ""),
            "status": status,
            "reason": reason,
            "blocker": blocker if status == "blocked" else None,
            "passed_rows": passed_rows,
            "posts_fetched": posts_fetched,
            "source_hint": "web + FB" if market.get("web") else "FB",
            "web_url": market.get("web") or market.get("reference_url") or "",
        })
    return rows
