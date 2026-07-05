#!/usr/bin/env python3
"""Gate C (Production / MALPH) verifier.

Checks:
- Gate B+ passes
- MALPH completion checks pass
- launchd/systemd configuration is installed and loaded
- Scrape duration of latest run is < 300 seconds
- Specials board coverage has active specials
- Five Islands has valid disposition (blocked/partial with reason or manually imported price)
"""
from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from board_render import build_board
from state import read_jsonl, latest_run_log


class GateFailure(Exception):
    pass


def _fail(msg: str) -> None:
    raise GateFailure(msg)


def check_gate_bplus() -> None:
    py = sys.executable
    proc = subprocess.run(
        [py, str(ROOT / "scripts" / "verify_next_gate.py")],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        _fail(f"Gate B+ failed:\n{proc.stdout}\n{proc.stderr}")


def check_malph_completion() -> None:
    proc = subprocess.run(
        ["bash", str(ROOT / "scripts" / "verify_completion.sh")],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        _fail(f"MALPH completion checks failed:\n{proc.stdout}\n{proc.stderr}")


def check_scheduling() -> None:
    if sys.platform == "darwin":
        # Check launchd
        proc = subprocess.run(
            ["launchctl", "list"],
            capture_output=True,
            text=True,
        )
        output = proc.stdout
        scrape_found = False
        serve_found = False
        serve_running = False
        
        for line in output.splitlines():
            parts = line.split()
            if len(parts) >= 3:
                label = parts[2]
                if label == "com.erik.lobster-price-monitor.scrape":
                    scrape_found = True
                elif label == "com.erik.lobster-price-monitor.serve":
                    serve_found = True
                    if parts[0] != "-" and int(parts[0]) > 0:
                        serve_running = True
                        
        if not scrape_found:
            _fail("launchd agent 'com.erik.lobster-price-monitor.scrape' not loaded")
        if not serve_found:
            _fail("launchd agent 'com.erik.lobster-price-monitor.serve' not loaded")
        if not serve_running:
            _fail("launchd agent 'com.erik.lobster-price-monitor.serve' is loaded but not running")
            
    elif sys.platform.startswith("linux"):
        # Check systemd
        proc = subprocess.run(
            ["systemctl", "is-active", "lobster-price-monitor-serve"],
            capture_output=True,
            text=True,
        )
        if "active" not in proc.stdout:
            _fail("systemd service 'lobster-price-monitor-serve' is not active")
            
        proc2 = subprocess.run(
            ["systemctl", "list-timers", "--all"],
            capture_output=True,
            text=True,
        )
        if "lobster-price-monitor-scrape" not in proc2.stdout:
            _fail("systemd timer 'lobster-price-monitor-scrape' not found")
    else:
        print("  ! Unknown OS — skipping scheduling verification")


def check_scrape_duration() -> None:
    run = latest_run_log()
    if not run:
        _fail("no run-log entry found")
    duration = run.get("duration_seconds")
    if duration is None:
        _fail("latest run-log entry lacks 'duration_seconds'")
    if duration > 300.0:
        _fail(f"scrape duration too slow: {duration:.2f}s (max 300s)")
    print(f"  ✓ latest scrape duration: {duration:.2f}s")


def check_specials_board() -> None:
    board = build_board()
    specials = board.get("sections", {}).get("special", [])
    if not specials:
        # Check if there are active specials in prices.jsonl
        rows = [
            r for r in read_jsonl("prices.jsonl")
            if r.get("kind") == "special" and r.get("gate_passed") is not False
        ]
        if rows:
            _fail("specials exist in prices.jsonl but none rendered on board")
        else:
            print("  ! no specials in prices.jsonl to display")
    else:
        print(f"  ✓ specials section has {len(specials)} items on board")


def check_five_islands_disposition() -> None:
    board = build_board()
    coverage = {c["name"]: c for c in board.get("market_coverage", [])}
    five_islands = coverage.get("Five Islands Lobster Co.", {})
    if not five_islands:
        _fail("Five Islands Lobster Co. missing from market coverage")
        
    status = five_islands.get("status")
    reason = five_islands.get("reason", "")
    
    # Check if there's a manual import row for Five Islands
    rows = [
        r for r in read_jsonl("prices.jsonl")
        if r.get("market") == "Five Islands Lobster Co." and r.get("source") == "manual"
    ]
    
    if rows:
        if status != "live":
            _fail(f"manual price imported for Five Islands but status is '{status}' instead of 'live'")
        print("  ✓ Five Islands is live via manual import")
    else:
        if status not in ("blocked", "partial"):
            _fail(f"Five Islands has no manual price and status is '{status}' (should be blocked/partial)")
        if not reason or "fetched but no prices" not in reason.lower() and "menu reference" not in reason.lower() and "unavailable" not in reason.lower():
            _fail(f"Five Islands blocker reason is invalid or missing: '{reason}'")
        print(f"  ✓ Five Islands is correctly quarantined/blocked: '{reason}'")


def main() -> int:
    print("=== Gate C production verification ===")
    checks: list[tuple[str, str]] = []
    
    steps = [
        ("gate_bplus", check_gate_bplus),
        ("malph_completion", check_malph_completion),
        ("scheduling", check_scheduling),
        ("scrape_duration", check_scrape_duration),
        ("specials_board", check_specials_board),
        ("five_islands_disposition", check_five_islands_disposition),
    ]
    
    failed = False
    for name, fn in steps:
        try:
            fn()
            checks.append((name, "pass"))
        except GateFailure as e:
            print(f"  ✗ {name} failed: {e}", file=sys.stderr)
            checks.append((name, "FAIL"))
            failed = True
        except Exception as e:
            print(f"  ✗ {name} error: {type(e).__name__}: {e}", file=sys.stderr)
            checks.append((name, "ERROR"))
            failed = True
            
    print()
    if failed:
        print("GATE C PRODUCTION VERIFICATION FAILED", file=sys.stderr)
        return 1
        
    print("GATE C PRODUCTION VERIFICATION PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
