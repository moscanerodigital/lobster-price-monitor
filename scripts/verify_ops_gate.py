#!/usr/bin/env python3
"""Gate D (Ops) verifier.

Checks:
- Gate C passes (verify_production_gate with --skip-scheduling)
- RALPH Learnings section populated from run-log
- Scheduler has alerts enabled (host only, skippable in CI)
- Latest run-log has alerts_enabled OR scheduler configured for alerts
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from state import latest_run_log
from update_ralph_learnings import DEFAULT_RALPH, learnings_populated


class GateFailure(Exception):
    pass


def _fail(msg: str) -> None:
    raise GateFailure(msg)


def check_gate_c(*, skip_scheduling: bool) -> None:
    py = sys.executable
    cmd = [py, str(ROOT / "scripts" / "verify_production_gate.py")]
    if skip_scheduling:
        cmd.append("--skip-scheduling")
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    if proc.returncode != 0:
        _fail(f"Gate C failed:\n{proc.stdout}\n{proc.stderr}")
    print("  ✓ Gate C production verification passed")


def check_ralph_learnings(*, ralph_path: Path) -> None:
    if not ralph_path.exists():
        _fail(f"RALPH.md not found at {ralph_path}")
    text = ralph_path.read_text(encoding="utf-8")
    if not learnings_populated(text):
        _fail(
            "RALPH Learnings section is empty or placeholder — "
            "run scripts/update_ralph_learnings.py"
        )
    print("  ✓ RALPH Learnings populated from run-log")


def _text_has_alerts_flag(text: str) -> bool:
    lowered = text.lower()
    if "lobster_alerts=1" in lowered.replace(" ", ""):
        return True
    if re.search(r"lobster_alerts\s*=\s*1", text, re.IGNORECASE):
        return True
    if re.search(r"lobster_alerts\s*=\s*true", text, re.IGNORECASE):
        return True
    if "--alerts" in text and "--no-alerts" not in text:
        return True
    return False


def _scheduler_alerts_enabled() -> bool:
    lobster_root = os.environ.get("LOBSTER_ROOT", str(ROOT))

    if sys.platform == "darwin":
        candidates = [
            Path.home() / "Library/LaunchAgents/com.erik.lobster-price-monitor.scrape.plist",
            Path.home()
            / "Library/LaunchAgents/com.erik.lobster-price-monitor.scrape.ops.plist",
            Path(lobster_root)
            / "deploy/launchd/com.erik.lobster-price-monitor.scrape.ops.plist",
            Path(lobster_root)
            / "deploy/launchd/com.erik.lobster-price-monitor.scrape.plist",
        ]
        for path in candidates:
            if path.exists():
                if _text_has_alerts_flag(path.read_text(encoding="utf-8")):
                    return True
        return False

    if sys.platform.startswith("linux"):
        for unit in (
            "lobster-price-monitor-scrape",
            "lobster-price-monitor-scrape.ops",
        ):
            proc = subprocess.run(
                ["systemctl", "cat", unit],
                capture_output=True,
                text=True,
            )
            if proc.returncode == 0 and _text_has_alerts_flag(proc.stdout):
                return True
        ops_service = Path(lobster_root) / "deploy/systemd/lobster-price-monitor-scrape.ops.service"
        if ops_service.exists() and _text_has_alerts_flag(
            ops_service.read_text(encoding="utf-8")
        ):
            return True
        return False

    print("  ! Unknown OS — skipping scheduler alerts verification")
    return True


def check_alerts_enabled(*, skip_alerts_check: bool) -> None:
    if skip_alerts_check:
        print("  ! alerts check skipped (CI mode)")
        return

    run = latest_run_log() or {}
    run_has_alerts = bool(run.get("alerts_enabled"))
    scheduler_has_alerts = _scheduler_alerts_enabled()

    if run_has_alerts:
        print("  ✓ latest run-log has alerts_enabled=true")
        return
    if scheduler_has_alerts:
        print("  ✓ scheduler configured for alerts (LOBSTER_ALERTS=1 or --alerts)")
        return

    _fail(
        "alerts not enabled: latest run-log has alerts_enabled=false and "
        "scheduler lacks LOBSTER_ALERTS=1 / --alerts"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Gate D (Ops) for lobster-price-monitor")
    parser.add_argument(
        "--skip-scheduling",
        action="store_true",
        help="Pass through to Gate C verifier (skip launchd/systemd checks)",
    )
    parser.add_argument(
        "--skip-alerts-check",
        action="store_true",
        help="Skip scheduler/run-log alerts verification (for CI)",
    )
    parser.add_argument(
        "--ralph-path",
        type=Path,
        default=DEFAULT_RALPH,
        help="Path to RALPH.md",
    )
    args = parser.parse_args()

    print("=== Gate D ops verification ===")
    checks: list[tuple[str, str]] = []
    failed = False

    steps = [
        ("gate_c", lambda: check_gate_c(skip_scheduling=True)),
        ("ralph_learnings", lambda: check_ralph_learnings(ralph_path=args.ralph_path)),
        (
            "alerts_enabled",
            lambda: check_alerts_enabled(skip_alerts_check=args.skip_alerts_check),
        ),
    ]

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
        print("GATE D OPS VERIFICATION FAILED", file=sys.stderr)
        return 1

    print("GATE D OPS VERIFICATION PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
