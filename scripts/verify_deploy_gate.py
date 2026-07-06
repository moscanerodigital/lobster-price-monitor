#!/usr/bin/env python3
"""Gate Deploy verifier (Gate D Wave 4).

Checks:
- make verify / unit test suite passes
- data/board.html exists
- health_check.py exits 0
- Dry-run scheduler loaded, ops scheduler NOT loaded (host only)
- Serve unit running (host only)
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from board_render import get_board, render_html
from state import DATA_DIR, latest_run_log
from verify_production_gate import (
    DRY_RUN_SCRAPE_LABEL,
    DRY_RUN_SCRAPE_TIMER,
    OPS_SCRAPE_LABEL,
    OPS_SCRAPE_TIMER,
    SERVE_LABEL,
    GateFailure,
    _fail,
    _launchctl_labels,
    _launchctl_pid,
)


def check_verify_suite() -> None:
    proc = subprocess.run(
        ["make", "verify-core"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        _fail(f"make verify-core failed:\n{proc.stdout}\n{proc.stderr}")
    print("  ✓ make verify-core passed")


def check_board_html() -> None:
    board = DATA_DIR / "board.html"
    if not board.exists():
        _fail(f"board.html missing at {board}")
    if board.stat().st_size == 0:
        _fail("board.html exists but is empty")
    print("  ✓ data/board.html exists")


def check_board_no_demo() -> None:
    """Production board must not be demo mode or carry demo HTML markers."""
    live = get_board(demo=False)
    if live.get("is_demo"):
        _fail("production board is in demo mode — run scrape first")
    board_path = DATA_DIR / "board.html"
    if board_path.exists():
        text = board_path.read_text(encoding="utf-8").lower()
        if 'class="demo-banner"' in text or "demo board" in text:
            _fail("board.html contains demo markers")
    print("  ✓ board has no demo markers")


def check_board_matches_data() -> None:
    """On-disk board.html must match a fresh render from current prices.jsonl."""
    board_path = DATA_DIR / "board.html"
    if not board_path.exists():
        return
    expected = render_html(get_board(demo=False))
    actual = board_path.read_text(encoding="utf-8")
    if actual != expected:
        _fail(
            "board.html is stale vs current data — re-run scrape or: "
            ".venv/bin/python scripts/board.py --html"
        )
    run = latest_run_log()
    if run and run.get("ts"):
        print("  ✓ board.html matches current data (run-log present)")
    else:
        print("  ✓ board.html matches current data")


def check_health() -> None:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "health_check.py")],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        _fail(f"health_check.py failed:\n{proc.stdout}\n{proc.stderr}")
    print("  ✓ health_check.py passed")


def check_dry_run_scheduler_loaded() -> None:
    if sys.platform == "darwin":
        proc = subprocess.run(
            ["launchctl", "list"],
            capture_output=True,
            text=True,
        )
        labels = _launchctl_labels(proc.stdout)
        if DRY_RUN_SCRAPE_LABEL not in labels:
            _fail(
                f"dry-run launchd agent '{DRY_RUN_SCRAPE_LABEL}' not loaded — "
                "run scripts/install_scheduler.sh"
            )
        if OPS_SCRAPE_LABEL in labels:
            _fail(
                f"ops launchd agent '{OPS_SCRAPE_LABEL}' is loaded — "
                "deploy gate expects dry-run only (promote later with promote_ops.sh)"
            )
        print(f"  ✓ dry-run launchd scrape loaded ({DRY_RUN_SCRAPE_LABEL})")

    elif sys.platform.startswith("linux"):
        dry_proc = subprocess.run(
            ["systemctl", "is-enabled", "lobster-price-monitor-scrape.timer"],
            capture_output=True,
            text=True,
        )
        dry_enabled = dry_proc.returncode == 0 and "enabled" in dry_proc.stdout
        if not dry_enabled:
            _fail(
                f"dry-run systemd timer '{DRY_RUN_SCRAPE_TIMER}' not enabled — "
                "run scripts/install_scheduler.sh"
            )

        ops_proc = subprocess.run(
            ["systemctl", "is-enabled", "lobster-price-monitor-scrape.ops.timer"],
            capture_output=True,
            text=True,
        )
        if ops_proc.returncode == 0 and "enabled" in ops_proc.stdout:
            _fail(
                f"ops systemd timer '{OPS_SCRAPE_TIMER}' is enabled — "
                "deploy gate expects dry-run only"
            )
        print(f"  ✓ dry-run systemd scrape timer enabled ({DRY_RUN_SCRAPE_TIMER})")

    else:
        print("  ! Unknown OS — skipping dry-run scheduler verification")


def check_serve_running() -> None:
    if sys.platform == "darwin":
        proc = subprocess.run(
            ["launchctl", "list"],
            capture_output=True,
            text=True,
        )
        output = proc.stdout
        labels = _launchctl_labels(output)
        if SERVE_LABEL not in labels:
            _fail(f"launchd agent '{SERVE_LABEL}' not loaded")
        serve_pid = _launchctl_pid(output, SERVE_LABEL)
        if serve_pid is None or serve_pid <= 0:
            _fail(f"launchd agent '{SERVE_LABEL}' is loaded but not running")
        print(f"  ✓ launchd serve agent running ({SERVE_LABEL}, pid={serve_pid})")

    elif sys.platform.startswith("linux"):
        proc = subprocess.run(
            ["systemctl", "is-active", "lobster-price-monitor-serve"],
            capture_output=True,
            text=True,
        )
        if "active" not in proc.stdout:
            _fail("systemd service 'lobster-price-monitor-serve' is not active")
        print("  ✓ systemd serve service active")

    else:
        print("  ! Unknown OS — skipping serve verification")


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify deploy gate for lobster-price-monitor")
    parser.add_argument(
        "--skip-scheduling",
        action="store_true",
        help="Skip scheduler/serve checks (for CI smoke tests)",
    )
    parser.add_argument(
        "--skip-verify-suite",
        action="store_true",
        help="Skip make verify-core (caller already ran it; avoids recursion in CI tests)",
    )
    args = parser.parse_args()

    print("=== Gate Deploy verification ===")
    failed = False

    steps: list[tuple[str, object]] = [
        ("board_html", check_board_html),
        ("board_no_demo", check_board_no_demo),
        ("board_matches_data", check_board_matches_data),
        ("health", check_health),
    ]
    if not args.skip_verify_suite:
        steps.insert(0, ("verify_suite", check_verify_suite))
    if not args.skip_scheduling:
        steps.extend(
            [
                ("dry_run_scheduler", check_dry_run_scheduler_loaded),
                ("serve_running", check_serve_running),
            ]
        )

    for name, fn in steps:
        try:
            fn()  # type: ignore[operator]
        except GateFailure as e:
            print(f"  ✗ {name} failed: {e}", file=sys.stderr)
            failed = True
        except Exception as e:
            print(f"  ✗ {name} error: {type(e).__name__}: {e}", file=sys.stderr)
            failed = True

    print()
    if failed:
        print("GATE DEPLOY VERIFICATION FAILED", file=sys.stderr)
        return 1

    print("GATE DEPLOY VERIFICATION PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
