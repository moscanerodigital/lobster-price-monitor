"""Market coverage status — per-market passed/blocked tracking for AAA gate."""

from __future__ import annotations

from collections import Counter

from market_names import short_market
from markets import MARKETS


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
        r.get("market", "") for r in read_jsonl("prices.jsonl") if r.get("gate_passed", True)
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

        rows.append(
            {
                "name": name,
                "short": short_market(name),
                "location": market.get("location", ""),
                "status": status,
                "reason": reason,
                "blocker": blocker if status == "blocked" else None,
                "passed_rows": passed_rows,
                "posts_fetched": posts_fetched,
                "source_hint": "web + FB" if market.get("web") else "FB",
                "web_url": market.get("web") or market.get("reference_url") or "",
            }
        )
    return rows
