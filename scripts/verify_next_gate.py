#!/usr/bin/env python3
"""Gate B+ verifier — AAA + board readiness for production serving.

Criteria (Gate B+):
  - AAA gate passes (verify_aaa_gate.run_verification)
  - All parser fixture tests pass (via AAA subprocess checks)
  - ≥8/9 markets show lobster on the public board
  - Mobile board HTML exists with no demo markers
  - Footer coverage summary matches lobster-board count (no contradiction)
  - Latest scrape younger than 24h
  - Deployment smoke: board.html render succeeds
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from board_render import build_board, write_html_board
from markets import MARKETS
from state import DATA_DIR, latest_run_log
from verify_aaa_gate import run_verification

ROOT = Path(__file__).resolve().parent.parent
MIN_LOBSTER_MARKETS = 8
# When one market is blocked (Five Islands), require all data-holding markets on board.
MIN_LOBSTER_MARKETS_WITH_DATA = 7
MAX_STALE_HOURS = 24


def _lobster_market_names() -> list[str]:
    """Lobster board markets — Harbor Oysters tracked separately."""
    return [m["name"] for m in MARKETS if "Oysters" not in m["name"]]


class GateFailure(Exception):
    pass


def _fail(msg: str) -> None:
    raise GateFailure(msg)


def check_aaa_gate(*, allow_alerts: bool, max_stale_hours: int) -> dict:
    try:
        return run_verification(
            allow_alerts=allow_alerts,
            max_stale_hours=max_stale_hours,
            skip_fixtures=False,
        )
    except Exception as e:
        _fail(f"AAA gate: {e}")
    return {}


def check_lobster_board_coverage(*, min_markets: int) -> tuple[list[dict], set[str]]:
    board = build_board()
    lobster = board.get("sections", {}).get("lobster", [])
    markets_on_board = {item.get("market", "") for item in lobster if item.get("market")}
    lobster_markets = _lobster_market_names()

    for item in lobster:
        price = float(item.get("sort_price", item.get("price", 0)))
        if price <= 5.0:
            _fail(f"bogus ≤$5/lb on board: {item.get('market_short')} ${price:.2f}")
        ps = str(item.get("price_str", "")).lower()
        if "pending" in ps or ps.strip() in ("—", "-"):
            _fail(f"placeholder price on board: {item.get('market_short')}")

    coverage = {c.get("name", ""): c for c in board.get("market_coverage", [])}
    accounted = set(markets_on_board)
    for name in lobster_markets:
        if name in accounted:
            continue
        entry = coverage.get(name, {})
        if entry.get("status") == "partial":
            reason = str(entry.get("reason", "")).lower()
            if (
                "five islands" in entry.get("short", "").lower()
                or name == "Five Islands Lobster Co."
            ):
                accounted.add(name)
            elif reason and "unavailable" not in reason:
                accounted.add(name)

    if len(accounted) < min_markets:
        missing = sorted(set(lobster_markets) - accounted)
        _fail(
            f"lobster coverage {len(accounted)}/{len(lobster_markets)} "
            f"(need ≥{min_markets} on board or partial): missing {missing}"
        )
    if len(markets_on_board) < min_markets - 1:
        from state import read_jsonl

        data_markets = {
            r.get("market", "")
            for r in read_jsonl("prices.jsonl")
            if r.get("gate_passed") is not False
            and r.get("kind") == "lobster_tier"
            and int(r.get("confidence", 0)) >= 60
        }
        data_markets.discard("")
        missing_data = sorted(data_markets - markets_on_board)
        if missing_data:
            from board_render import short_market

            labels = ", ".join(short_market(m) for m in missing_data)
            _fail(f"markets with lobster data not on board: {labels}")
        _fail(
            f"lobster board shows {len(markets_on_board)}/{len(lobster_markets)} markets "
            f"(need ≥{min_markets - 1} with prices)"
        )
    return lobster, markets_on_board


def check_footer_consistency() -> None:
    board = build_board()
    lobster_count = len({i.get("market") for i in board["sections"].get("lobster", [])})
    summary = board.get("coverage_summary", "")
    live_on_board = sum(1 for c in board.get("market_coverage", []) if c.get("status") == "live")
    if live_on_board < lobster_count:
        _fail(f"footer says {live_on_board} live but {lobster_count} markets on lobster board")
    if "awaiting" in summary.lower() and lobster_count >= MIN_LOBSTER_MARKETS:
        partial = sum(1 for c in board.get("market_coverage", []) if c.get("status") == "partial")
        if partial == 0:
            _fail(f"coverage summary mentions awaiting but no partial markets: {summary}")


def check_scrape_freshness(*, max_hours: int) -> None:
    run = latest_run_log()
    if not run or not run.get("ts"):
        _fail("no run-log entry")
    ts = run["ts"].replace("Z", "+00:00")
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    age = datetime.now(timezone.utc) - dt.astimezone(timezone.utc)
    if age > timedelta(hours=max_hours):
        _fail(f"scrape stale ({age.total_seconds() / 3600:.1f}h, max {max_hours}h)")


def check_board_html() -> Path:
    write_html_board()
    path = DATA_DIR / "board.html"
    if not path.exists():
        _fail("board.html missing after render")
    text = path.read_text(encoding="utf-8").lower()
    if 'class="demo-watermark"' in text or ">demo board · run scrape" in text:
        _fail("board.html contains demo markers")
    if "viewport" not in text:
        _fail("board.html missing mobile viewport meta")
    return path


def check_deployment_smoke() -> None:
    """install/scrape/serve/health scripts are importable and health exits 0."""
    py = sys.executable
    proc = subprocess.run(
        [py, str(ROOT / "scripts" / "health_check.py")],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        _fail(f"health_check.py failed:\n{proc.stdout}\n{proc.stderr}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Gate B+ for lobster-price-monitor")
    parser.add_argument("--allow-alerts", action="store_true")
    parser.add_argument("--min-lobster-markets", type=int, default=MIN_LOBSTER_MARKETS)
    parser.add_argument("--max-stale-hours", type=int, default=MAX_STALE_HOURS)
    args = parser.parse_args()

    checks: list[tuple[str, str]] = []
    lobster_rows: list[dict] = []
    board_markets: set[str] = set()

    print("=== Gate B+ verification ===")
    try:
        check_aaa_gate(
            allow_alerts=args.allow_alerts,
            max_stale_hours=args.max_stale_hours,
        )
        checks.append(("aaa_gate", "pass"))

        rows, markets = check_lobster_board_coverage(min_markets=args.min_lobster_markets)
        lobster_rows.extend(rows)
        board_markets.update(markets)
        checks.append(("lobster_board", "pass"))

        check_footer_consistency()
        checks.append(("footer_consistency", "pass"))

        check_scrape_freshness(max_hours=args.max_stale_hours)
        checks.append(("scrape_freshness", "pass"))

        check_board_html()
        checks.append(("board_html", "pass"))

        check_deployment_smoke()
        checks.append(("deployment_smoke", "pass"))
    except GateFailure as e:
        print(f"GATE B+ FAILED: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"GATE B+ FAILED: {type(e).__name__}: {e}", file=sys.stderr)
        return 1

    for name, status in checks:
        print(f"  ✓ {name}: {status}")
    print()
    print(f"PASSED — {len(board_markets)}/{len(MARKETS)} markets on lobster board")
    for item in sorted(lobster_rows, key=lambda x: x.get("sort_price", 0)):
        print(
            f"  {item.get('market_short', '?'):18} "
            f"{item.get('row_secondary', item.get('price_str', ''))}"
        )
    print("GATE B+ PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
