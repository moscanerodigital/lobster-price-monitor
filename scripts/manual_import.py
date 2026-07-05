#!/usr/bin/env python3
"""Manual price import tool — append custom price to prices.jsonl and re-render board."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from state import PARSER_VERSION, append_jsonl
from board_render import write_html_board, short_market


def slugify(name: str) -> str:
    return name.lower().replace("co.", "").replace("market", "").replace("&", "and").strip().replace(" ", "-")


def main() -> int:
    parser = argparse.ArgumentParser(description="Manually import a price row into the seafood board")
    parser.add_argument("--market", default="Five Islands Lobster Co.", help="Market name")
    parser.add_argument("--tier", default="soft_shell", help="Price tier (e.g. chicks, soft_shell, hard_shell, halibut, etc.)")
    parser.add_argument("--price", type=float, required=True, help="Price amount (e.g. 10.99)")
    parser.add_argument("--unit", default="lb", choices=["lb", "doz", "ea"], help="Price unit")
    parser.add_argument("--kind", default="lobster_tier", choices=["lobster_tier", "oyster_tier", "special"], help="Kind of tier")
    args = parser.parse_args()

    now_iso = datetime.now(timezone.utc).isoformat()
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    slug = slugify(args.market)
    post_id = f"manual-{slug}-{day}"

    row = {
        "market": args.market,
        "observed_at": now_iso,
        "post_id": post_id,
        "kind": args.kind,
        "key": args.tier,
        "price": args.price,
        "unit": args.unit,
        "snippet": f"Manual import: {args.tier} ${args.price:.2f}/{args.unit}",
        "confidence": 100,
        "source_quality": 1.0,
        "gate_passed": True,
        "source": "manual",
        "source_url": "",
        "fetch_timestamp": now_iso,
        "parser_version": PARSER_VERSION,
        "gate_details": {
            "gate_a": True,
            "gate_b": True,
            "gate_c": True,
            "raw_confidence": 100,
        },
    }

    append_jsonl("prices.jsonl", row)
    print(f"Imported manual price: {args.market} — {args.tier} at ${args.price:.2f}/{args.unit}", flush=True)

    try:
        board_path = write_html_board()
        print(f"Board regenerated successfully at {board_path}", flush=True)
    except Exception as e:
        print(f"Error regenerating board: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
