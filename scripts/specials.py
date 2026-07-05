#!/usr/bin/env python3
"""Query CLI for gated seafood specials from prices.jsonl."""
from __future__ import annotations
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from state import read_jsonl, DATA_DIR


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
    now = datetime.now(timezone.utc)
    return dt.date() == now.date()


def query_specials(
    *,
    today_only: bool = False,
    market: str | None = None,
    min_confidence: int = 0,
    limit: int = 50,
) -> list[dict]:
    rows = read_jsonl("prices.jsonl")
    results: list[dict] = []
    for r in rows:
        if r.get("kind") != "special":
            continue
        if r.get("gate_passed") is False:
            continue
        conf = int(r.get("confidence", 0))
        if conf < min_confidence:
            continue
        if market and market.lower() not in r.get("market", "").lower():
            continue
        observed = r.get("observed_at", "")
        if today_only and not _is_today(observed):
            continue
        results.append(r)
    results.sort(key=lambda x: x.get("observed_at", ""), reverse=True)
    return results[:limit]


def main() -> int:
    parser = argparse.ArgumentParser(description="Browse gated seafood specials")
    parser.add_argument("--today", action="store_true", help="Only today's specials")
    parser.add_argument("--market", type=str, help="Filter by market name substring")
    parser.add_argument("--min-confidence", type=int, default=70, help="Min confidence (default 70)")
    parser.add_argument("--limit", type=int, default=50, help="Max rows to show")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    if not (DATA_DIR / "prices.jsonl").exists():
        print("No prices.jsonl found. Run scrape_markets.py first.", file=sys.stderr)
        return 1

    rows = query_specials(
        today_only=args.today,
        market=args.market,
        min_confidence=args.min_confidence,
        limit=args.limit,
    )

    if args.json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
        return 0

    if not rows:
        print("No gated specials found matching criteria.")
        return 0

    for r in rows:
        conf = r.get("confidence", "?")
        print(
            f"{r.get('market', '?')} | {r.get('key', '?')} "
            f"${r.get('price', 0):.2f}/{r.get('unit', '?')} "
            f"(conf {conf}) | {r.get('observed_at', '')[:19]}"
        )
    print(f"\n{len(rows)} special(s) shown.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
