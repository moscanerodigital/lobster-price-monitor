#!/usr/bin/env python3
"""Display the Maine Coast seafood board — terminal or HTML."""
from __future__ import annotations
import argparse
import sys
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from board_render import get_board, render_html, render_terminal, write_html_board


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Maine Coast seafood board — chalkboard-style price display",
    )
    parser.add_argument("--html", action="store_true", help="Write data/board.html and optionally open it")
    parser.add_argument("--open", action="store_true", help="Open board.html in browser (with --html)")
    parser.add_argument("--demo", action="store_true", help="Show demo board when no live data")
    parser.add_argument("--today", action="store_true", help="Only today's gated prices")
    parser.add_argument("--market", type=str, help="Filter by market name")
    parser.add_argument("--min-confidence", type=int, default=70)
    parser.add_argument("-o", "--output", type=str, help="HTML output path (default: data/board.html)")
    args = parser.parse_args()

    kwargs = {
        "min_confidence": args.min_confidence,
        "today_only": args.today,
        "market": args.market,
        "demo": args.demo,
    }

    if args.html:
        out = write_html_board(
            Path(args.output) if args.output else None,
            **kwargs,
        )
        print(f"Board written to {out}")
        if args.open:
            webbrowser.open(out.as_uri())
        return 0

    board = get_board(**kwargs)
    print(render_terminal(board))
    return 0


if __name__ == "__main__":
    sys.exit(main())
