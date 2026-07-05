#!/usr/bin/env python3
"""Readiness/health report for lobster-price-monitor serving host."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from market_coverage import build_market_coverage
from state import DATA_DIR, ensure_logs_dir, latest_run_log, read_jsonl


def build_report() -> dict:
    run = latest_run_log() or {}
    coverage = build_market_coverage()
    prices = [r for r in read_jsonl("prices.jsonl") if r.get("gate_passed") is not False]
    quarantined = read_jsonl("quarantine.jsonl")
    board_exists = (DATA_DIR / "board.html").exists()

    return {
        "status": "ready" if board_exists and run and prices else "degraded",
        "latest_run_timestamp": run.get("ts"),
        "alerts_enabled_last_run": run.get("alerts_enabled", False),
        "alerts_suppressed_last_run": run.get("alerts_suppressed", 0),
        "passed_row_count": len(prices),
        "quarantined_row_count": len(quarantined),
        "board_html_exists": board_exists,
        "source_coverage": [
            {
                "market": c["name"],
                "status": c.get("status"),
                "passed_rows": c.get("passed_rows", 0),
                "posts_fetched": c.get("posts_fetched", 0),
                "blocker": c.get("blocker") or c.get("reason"),
                "source_used": c.get("source_used"),
            }
            for c in coverage
        ],
        "live_markets": [c["name"] for c in coverage if c.get("status") == "live"],
        "blocked_markets": [
            {"market": c["name"], "blocker": c.get("blocker") or c.get("reason")}
            for c in coverage
            if c.get("status") != "live"
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Health/readiness report")
    parser.add_argument(
        "--log",
        action="store_true",
        help="Append JSON report to logs/health.jsonl",
    )
    args = parser.parse_args()

    report = build_report()
    if args.log:
        log_path = ensure_logs_dir() / "health.jsonl"
        entry = {"ts": datetime.now(timezone.utc).isoformat(), **report}
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["status"] == "ready" else 1


if __name__ == "__main__":
    sys.exit(main())
