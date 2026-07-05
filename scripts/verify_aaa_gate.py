#!/usr/bin/env python3
"""AAA gate verifier — fails if production board/serving prerequisites are not met."""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from board_render import get_board, write_html_board
from market_coverage import build_market_coverage
from markets import MARKETS
from state import DATA_DIR, latest_run_log, read_jsonl

ROOT = Path(__file__).resolve().parent.parent
STALE_HOURS_DEFAULT = 48

REQUIRED_ROW_FIELDS = (
    "market",
    "source",
    "observed_at",
    "confidence",
    "snippet",
)


class GateFailure(Exception):
    pass


def _fail(msg: str) -> None:
    raise GateFailure(msg)


def check_no_demo_board() -> None:
    board = get_board(demo=False)
    if board.get("is_demo"):
        _fail("production board is in demo mode — run scrape first")
    for section in board.get("sections", {}).values():
        for item in section:
            ps = str(item.get("price_str", "")).lower()
            if "pending" in ps or ps.strip() in ("—", "-"):
                _fail(f"board item has placeholder price: {item.get('label')}")
    html_path = DATA_DIR / "board.html"
    if html_path.exists():
        text = html_path.read_text(encoding="utf-8").lower()
        if 'class="demo-watermark"' in text or ">demo board · run scrape" in text:
            _fail("board.html contains active demo markers in production mode")


def check_demo_explicit_only() -> None:
    demo = get_board(demo=True)
    if not demo.get("is_demo"):
        _fail("--demo board must set is_demo=True")
    live = get_board(demo=False)
    if live.get("is_demo"):
        _fail("default board must not be demo")


def check_row_provenance() -> None:
    from state import read_jsonl as _read

    rows = [r for r in _read("prices.jsonl") if r.get("gate_passed", True)]
    if not rows:
        _fail("prices.jsonl has no gated rows — run scrape with --no-alerts")
    history_urls = {
        str(r.get("post_id", "")): r.get("url", "")
        for r in _read("history.jsonl")
        if r.get("post_id") and r.get("url")
    }
    for row in rows:
        missing = [f for f in REQUIRED_ROW_FIELDS if not row.get(f)]
        if "parser_version" in missing and row.get("source") and row.get("snippet"):
            missing.remove("parser_version")
        if missing:
            _fail(f"row missing provenance {missing}: {row.get('market')} {row.get('key')}")
        source_url = row.get("source_url") or history_urls.get(str(row.get("post_id", "")), "")
        if not source_url and not row.get("post_id"):
            _fail(f"row lacks source_url/post_id: {row.get('market')} {row.get('key')}")


def check_market_coverage() -> list[dict]:
    coverage = build_market_coverage()
    if len(coverage) != len(MARKETS):
        _fail(f"market coverage has {len(coverage)} entries, expected {len(MARKETS)}")
    for entry in coverage:
        status = entry.get("status")
        if status not in ("live", "blocked", "partial"):
            _fail(f"unknown status for {entry.get('name')}: {status}")
        if status == "blocked" and not (entry.get("blocker") or entry.get("reason")):
            _fail(f"blocked market lacks blocker reason: {entry.get('name')}")
    return coverage


def check_alerts_disabled(*, allow_alerts: bool) -> None:
    run = latest_run_log()
    if not run:
        _fail("no run-log.jsonl entry — run scrape first")
    if run.get("alerts_enabled") and not allow_alerts:
        _fail("latest scrape had alerts_enabled=true — re-run with --no-alerts")


def check_scrape_freshness(*, max_hours: int) -> None:
    run = latest_run_log()
    if not run or not run.get("ts"):
        _fail("missing latest run timestamp")
    ts = run["ts"].replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(ts)
    except ValueError as e:
        _fail(f"invalid run timestamp: {e}")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    age = datetime.now(timezone.utc) - dt.astimezone(timezone.utc)
    if age > timedelta(hours=max_hours):
        _fail(f"latest scrape is stale ({age.total_seconds() / 3600:.1f}h old, max {max_hours}h)")


def check_parser_fixtures() -> None:
    py = sys.executable
    scripts = [
        "test_parse_web.py",
        "test_quality_gate.py",
        "test_parse.py",
        "test_specials.py",
        "test_aaa_gate.py",
    ]
    for name in scripts:
        path = ROOT / "scripts" / name
        if not path.exists():
            _fail(f"missing fixture test: {name}")
        proc = subprocess.run(
            [py, str(path)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            _fail(f"{name} failed (exit {proc.returncode}):\n{proc.stdout}\n{proc.stderr}")


def check_board_html_exists() -> None:
    if not (DATA_DIR / "board.html").exists():
        write_html_board()
    if not (DATA_DIR / "board.html").exists():
        _fail("data/board.html missing after board render")


def run_verification(
    *,
    allow_alerts: bool = False,
    max_stale_hours: int = STALE_HOURS_DEFAULT,
    skip_fixtures: bool = False,
) -> dict:
    checks: list[tuple[str, str]] = []
    coverage: list[dict] = []

    steps = [
        ("demo_explicit_only", lambda: check_demo_explicit_only()),
        ("no_demo_production", lambda: check_no_demo_board()),
        ("row_provenance", lambda: check_row_provenance()),
        ("market_coverage", lambda: coverage.extend(check_market_coverage()) or None),
        ("alerts_disabled", lambda: check_alerts_disabled(allow_alerts=allow_alerts)),
        ("scrape_freshness", lambda: check_scrape_freshness(max_hours=max_stale_hours)),
        ("board_html", lambda: check_board_html_exists()),
    ]
    if not skip_fixtures:
        steps.append(("parser_fixtures", lambda: check_parser_fixtures()))

    for name, fn in steps:
        try:
            fn()
            checks.append((name, "pass"))
        except GateFailure as e:
            checks.append((name, f"FAIL: {e}"))
            raise
        except Exception as e:
            checks.append((name, f"FAIL: {type(e).__name__}: {e}"))
            raise

    run = latest_run_log() or {}
    return {
        "status": "pass",
        "checks": checks,
        "market_coverage": coverage or build_market_coverage(),
        "latest_run_ts": run.get("ts"),
        "alerts_enabled": run.get("alerts_enabled"),
        "passed_rows": len([r for r in read_jsonl("prices.jsonl") if r.get("gate_passed", True)]),
        "quarantined_rows": len(read_jsonl("quarantine.jsonl")),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify AAA gate for lobster-price-monitor")
    parser.add_argument(
        "--allow-alerts",
        action="store_true",
        help="Do not fail when latest run had alerts enabled",
    )
    parser.add_argument(
        "--max-stale-hours",
        type=int,
        default=STALE_HOURS_DEFAULT,
        help=f"Fail if latest scrape older than N hours (default {STALE_HOURS_DEFAULT})",
    )
    parser.add_argument(
        "--skip-fixtures",
        action="store_true",
        help="Skip subprocess parser fixture tests",
    )
    args = parser.parse_args()

    print("=== AAA gate verification ===")
    try:
        report = run_verification(
            allow_alerts=args.allow_alerts,
            max_stale_hours=args.max_stale_hours,
            skip_fixtures=args.skip_fixtures,
        )
    except (GateFailure, Exception) as e:
        print(f"AAA GATE FAILED: {e}", file=sys.stderr)
        return 1

    for name, status in report["checks"]:
        mark = "✓" if status == "pass" else "✗"
        print(f"  {mark} {name}: {status}")
    print()
    print(f"PASSED — {report['passed_rows']} gated rows, {report['quarantined_rows']} quarantined")
    live = [c for c in report["market_coverage"] if c.get("status") == "live"]
    blocked = [c for c in report["market_coverage"] if c.get("status") == "blocked"]
    print(f"Markets live: {len(live)} | blocked: {len(blocked)}")
    for c in blocked:
        print(f"  BLOCKED {c.get('short', c.get('name'))}: {c.get('reason') or c.get('blocker')}")
    print("AAA GATE PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
