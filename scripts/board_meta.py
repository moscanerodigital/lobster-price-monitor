"""Build metadata for board.html generator comments and cache busting."""

from __future__ import annotations

import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def git_revision_short(repo_root: Path | None = None) -> str:
    root = repo_root or Path(__file__).resolve().parent.parent
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return "unknown"


def board_auto_refresh_seconds() -> int | None:
    """Return meta refresh interval, or None to omit the tag (CI/tests)."""
    if os.environ.get("BOARD_AUTO_REFRESH", "300").strip().lower() in {
        "0",
        "false",
        "off",
        "no",
    }:
        return None
    raw = os.environ.get("BOARD_AUTO_REFRESH", "300").strip()
    try:
        seconds = int(raw)
    except ValueError:
        seconds = 300
    return seconds if seconds > 0 else None


def generator_comment(
    *,
    gated_row_count: int,
    generated_at: str | None = None,
    live_markets: int = 0,
) -> str:
    """HTML comment documenting scrape → board pipeline (Herb audit E-07)."""
    ts = generated_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rev = git_revision_short()
    return (
        f" built by lobster-price-monitor: scrape→prices.jsonl→board_render; "
        f"{gated_row_count} gated rows; {live_markets} live markets; "
        f"commit {rev}; generated {ts} "
    )


def cache_bust_token(updated_at: str) -> str:
    """Compact token for ?v= query on board.html redirects."""
    dt_text = updated_at.strip()
    if not dt_text:
        return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    if dt_text.endswith("Z"):
        dt_text = dt_text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(dt_text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y%m%d-%H%M")
    except ValueError:
        return dt_text[:16].replace(":", "").replace("T", "-").replace(" ", "-")
