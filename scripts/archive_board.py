#!/usr/bin/env python3
"""Archive published board.html snapshots (Herb audit E-12)."""

from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from board_meta import git_revision_short
import state
from state import read_jsonl


def archive_board(*, board_path: Path | None = None) -> Path | None:
    """Copy board.html to data/archive/board-YYYY-MM-DD.html and append manifest."""
    data_dir = state.DATA_DIR
    src = (board_path or data_dir / "board.html").resolve()
    if not src.is_file():
        return None

    archive_dir = data_dir / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    dest = archive_dir / f"board-{day}.html"
    shutil.copy2(src, dest)

    gated = len(read_jsonl("prices.jsonl"))
    live_markets = 0
    try:
        coverage = json.loads((data_dir / "market-coverage.json").read_text(encoding="utf-8"))
        live_markets = sum(
            1 for m in coverage.get("markets", []) if m.get("status") == "live"
        )
    except (OSError, json.JSONDecodeError, AttributeError):
        pass

    manifest = archive_dir / "manifest.jsonl"
    entry = {
        "date": day,
        "archived_at": datetime.now(timezone.utc).isoformat(),
        "path": str(dest.relative_to(data_dir)),
        "gated_row_count": gated,
        "live_markets": live_markets,
        "commit": git_revision_short(),
    }
    with manifest.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return dest


def main() -> int:
    out = archive_board()
    if out is None:
        print("No board.html to archive", file=sys.stderr)
        return 1
    print(f"Archived → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
