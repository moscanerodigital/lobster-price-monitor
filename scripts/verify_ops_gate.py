#!/usr/bin/env python3
"""Gate D (Ops) verifier.

Checks:
- Gate C passes (verify_production_gate with --skip-scheduling)
- RALPH Learnings section populated from run-log
- Ops scheduler loaded and dry-run scheduler unloaded (host only, skippable in CI)
- Scheduler has alerts enabled (host only, skippable in CI)
- Latest run-log has alerts_enabled OR scheduler configured for alerts
- Watchdog loaded and recovery enabled on host (skippable in CI)
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
from verify_production_gate import (
    DRY_RUN_SCRAPE_LABEL,
    DRY_RUN_SCRAPE_TIMER,
    OPS_SCRAPE_LABEL,
    OPS_SCRAPE_TIMER,
    _launchctl_labels,
)

WATCHDOG_LABEL = "com.erik.lobster-price-monitor.watchdog"
WATCHDOG_TIMER = "lobster-price-monitor-watchdog.timer"


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


def _text_has_recover_flag(text: str) -> bool:
    lowered = text.lower()
    if "lobster_watchdog_recover=1" in lowered.replace(" ", ""):
        return True
    if re.search(r"lobster_watchdog_recover\s*=\s*1", text, re.IGNORECASE):
        return True
    if re.search(r"lobster_watchdog_recover\s*=\s*true", text, re.IGNORECASE):
        return True
    if re.search(
        r"<key>LOBSTER_WATCHDOG_RECOVER</key>\s*<string>1</string>",
        text,
        re.IGNORECASE,
    ):
        return True
    return False


def _text_has_deep_recover_flag(text: str) -> bool:
    lowered = text.lower()
    if "lobster_watchdog_deep_recover=1" in lowered.replace(" ", ""):
        return True
    if re.search(r"lobster_watchdog_deep_recover\s*=\s*1", text, re.IGNORECASE):
        return True
    if re.search(r"lobster_watchdog_deep_recover\s*=\s*true", text, re.IGNORECASE):
        return True
    if re.search(
        r"<key>LOBSTER_WATCHDOG_DEEP_RECOVER</key>\s*<string>1</string>",
        text,
        re.IGNORECASE,
    ):
        return True
    return False


def _text_has_redeploy_recover_flag(text: str) -> bool:
    lowered = text.lower()
    if "lobster_watchdog_redeploy_recover=1" in lowered.replace(" ", ""):
        return True
    if re.search(r"lobster_watchdog_redeploy_recover\s*=\s*1", text, re.IGNORECASE):
        return True
    if re.search(r"lobster_watchdog_redeploy_recover\s*=\s*true", text, re.IGNORECASE):
        return True
    if re.search(
        r"<key>LOBSTER_WATCHDOG_REDEPLOY_RECOVER</key>\s*<string>1</string>",
        text,
        re.IGNORECASE,
    ):
        return True
    return False


def _text_has_rebuild_recover_flag(text: str) -> bool:
    lowered = text.lower()
    if "lobster_watchdog_rebuild_recover=1" in lowered.replace(" ", ""):
        return True
    if re.search(r"lobster_watchdog_rebuild_recover\s*=\s*1", text, re.IGNORECASE):
        return True
    if re.search(r"lobster_watchdog_rebuild_recover\s*=\s*true", text, re.IGNORECASE):
        return True
    if re.search(
        r"<key>LOBSTER_WATCHDOG_REBUILD_RECOVER</key>\s*<string>1</string>",
        text,
        re.IGNORECASE,
    ):
        return True
    return False


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


def _ops_unit_has_alerts_flag() -> bool:
    lobster_root = os.environ.get("LOBSTER_ROOT", str(ROOT))

    if sys.platform == "darwin":
        ops_path = (
            Path.home()
            / "Library/LaunchAgents/com.erik.lobster-price-monitor.scrape.ops.plist"
        )
        if not ops_path.exists():
            ops_path = (
                Path(lobster_root)
                / "deploy/launchd/com.erik.lobster-price-monitor.scrape.ops.plist"
            )
        if ops_path.exists():
            return _text_has_alerts_flag(ops_path.read_text(encoding="utf-8"))
        return False

    if sys.platform.startswith("linux"):
        proc = subprocess.run(
            ["systemctl", "cat", "lobster-price-monitor-scrape.ops"],
            capture_output=True,
            text=True,
        )
        if proc.returncode == 0 and _text_has_alerts_flag(proc.stdout):
            return True
        ops_service = Path(lobster_root) / "deploy/systemd/lobster-price-monitor-scrape.ops.service"
        if ops_service.exists():
            return _text_has_alerts_flag(ops_service.read_text(encoding="utf-8"))
        return False

    return True


def check_ops_scheduler_loaded(*, skip_alerts_check: bool) -> None:
    if skip_alerts_check:
        print("  ! ops scheduler check skipped (CI mode)")
        return

    if sys.platform == "darwin":
        proc = subprocess.run(
            ["launchctl", "list"],
            capture_output=True,
            text=True,
        )
        labels = _launchctl_labels(proc.stdout)
        if OPS_SCRAPE_LABEL not in labels:
            _fail(
                f"ops launchd agent '{OPS_SCRAPE_LABEL}' not loaded — "
                "run scripts/promote_ops.sh"
            )
        if DRY_RUN_SCRAPE_LABEL in labels:
            _fail(
                f"dry-run launchd agent '{DRY_RUN_SCRAPE_LABEL}' still loaded — "
                "unload before ops promotion"
            )
        if not _ops_unit_has_alerts_flag():
            _fail("ops launchd plist lacks LOBSTER_ALERTS=1 or --alerts")
        print(f"  ✓ ops launchd agent loaded ({OPS_SCRAPE_LABEL})")

    elif sys.platform.startswith("linux"):
        ops_proc = subprocess.run(
            ["systemctl", "is-enabled", "lobster-price-monitor-scrape.ops.timer"],
            capture_output=True,
            text=True,
        )
        ops_enabled = ops_proc.returncode == 0 and "enabled" in ops_proc.stdout
        if not ops_enabled:
            _fail(
                f"ops systemd timer '{OPS_SCRAPE_TIMER}' not enabled — "
                "run scripts/promote_ops.sh"
            )

        dry_proc = subprocess.run(
            ["systemctl", "is-enabled", "lobster-price-monitor-scrape.timer"],
            capture_output=True,
            text=True,
        )
        if dry_proc.returncode == 0 and "enabled" in dry_proc.stdout:
            _fail(
                f"dry-run systemd timer '{DRY_RUN_SCRAPE_TIMER}' still enabled — "
                "disable before ops promotion"
            )
        if not _ops_unit_has_alerts_flag():
            _fail("ops systemd unit lacks LOBSTER_ALERTS=1 or --alerts")
        print(f"  ✓ ops systemd timer enabled ({OPS_SCRAPE_TIMER})")

    else:
        print("  ! Unknown OS — skipping ops scheduler verification")


def _watchdog_unit_has_recover_flag() -> bool:
    lobster_root = os.environ.get("LOBSTER_ROOT", str(ROOT))

    if sys.platform == "darwin":
        watchdog_path = (
            Path.home()
            / "Library/LaunchAgents/com.erik.lobster-price-monitor.watchdog.plist"
        )
        if not watchdog_path.exists():
            watchdog_path = (
                Path(lobster_root)
                / "deploy/launchd/com.erik.lobster-price-monitor.watchdog.plist"
            )
        if watchdog_path.exists():
            return _text_has_recover_flag(watchdog_path.read_text(encoding="utf-8"))
        return False

    if sys.platform.startswith("linux"):
        proc = subprocess.run(
            ["systemctl", "cat", "lobster-price-monitor-watchdog"],
            capture_output=True,
            text=True,
        )
        if proc.returncode == 0 and _text_has_recover_flag(proc.stdout):
            return True
        watchdog_service = Path(lobster_root) / "deploy/systemd/lobster-price-monitor-watchdog.service"
        if watchdog_service.exists():
            return _text_has_recover_flag(watchdog_service.read_text(encoding="utf-8"))
        return False

    return True


def _watchdog_unit_has_deep_recover_flag() -> bool:
    lobster_root = os.environ.get("LOBSTER_ROOT", str(ROOT))

    if sys.platform == "darwin":
        watchdog_path = (
            Path.home()
            / "Library/LaunchAgents/com.erik.lobster-price-monitor.watchdog.plist"
        )
        if not watchdog_path.exists():
            watchdog_path = (
                Path(lobster_root)
                / "deploy/launchd/com.erik.lobster-price-monitor.watchdog.plist"
            )
        if watchdog_path.exists():
            return _text_has_deep_recover_flag(watchdog_path.read_text(encoding="utf-8"))
        return False

    if sys.platform.startswith("linux"):
        proc = subprocess.run(
            ["systemctl", "cat", "lobster-price-monitor-watchdog"],
            capture_output=True,
            text=True,
        )
        if proc.returncode == 0 and _text_has_deep_recover_flag(proc.stdout):
            return True
        watchdog_service = Path(lobster_root) / "deploy/systemd/lobster-price-monitor-watchdog.service"
        if watchdog_service.exists():
            return _text_has_deep_recover_flag(watchdog_service.read_text(encoding="utf-8"))
        return False

    return True


def _watchdog_unit_has_redeploy_recover_flag() -> bool:
    lobster_root = os.environ.get("LOBSTER_ROOT", str(ROOT))

    if sys.platform == "darwin":
        watchdog_path = (
            Path.home()
            / "Library/LaunchAgents/com.erik.lobster-price-monitor.watchdog.plist"
        )
        if not watchdog_path.exists():
            watchdog_path = (
                Path(lobster_root)
                / "deploy/launchd/com.erik.lobster-price-monitor.watchdog.plist"
            )
        if watchdog_path.exists():
            return _text_has_redeploy_recover_flag(watchdog_path.read_text(encoding="utf-8"))
        return False

    if sys.platform.startswith("linux"):
        proc = subprocess.run(
            ["systemctl", "cat", "lobster-price-monitor-watchdog"],
            capture_output=True,
            text=True,
        )
        if proc.returncode == 0 and _text_has_redeploy_recover_flag(proc.stdout):
            return True
        watchdog_service = Path(lobster_root) / "deploy/systemd/lobster-price-monitor-watchdog.service"
        if watchdog_service.exists():
            return _text_has_redeploy_recover_flag(watchdog_service.read_text(encoding="utf-8"))
        return False

    return True


def _watchdog_unit_has_rebuild_recover_flag() -> bool:
    lobster_root = os.environ.get("LOBSTER_ROOT", str(ROOT))

    if sys.platform == "darwin":
        watchdog_path = (
            Path.home()
            / "Library/LaunchAgents/com.erik.lobster-price-monitor.watchdog.plist"
        )
        if not watchdog_path.exists():
            watchdog_path = (
                Path(lobster_root)
                / "deploy/launchd/com.erik.lobster-price-monitor.watchdog.plist"
            )
        if watchdog_path.exists():
            return _text_has_rebuild_recover_flag(watchdog_path.read_text(encoding="utf-8"))
        return False

    if sys.platform.startswith("linux"):
        proc = subprocess.run(
            ["systemctl", "cat", "lobster-price-monitor-watchdog"],
            capture_output=True,
            text=True,
        )
        if proc.returncode == 0 and _text_has_rebuild_recover_flag(proc.stdout):
            return True
        watchdog_service = Path(lobster_root) / "deploy/systemd/lobster-price-monitor-watchdog.service"
        if watchdog_service.exists():
            return _text_has_rebuild_recover_flag(watchdog_service.read_text(encoding="utf-8"))
        return False

    return True


def check_watchdog_loaded(*, skip_alerts_check: bool) -> None:
    if skip_alerts_check:
        print("  ! watchdog check skipped (CI mode)")
        return

    if sys.platform == "darwin":
        proc = subprocess.run(
            ["launchctl", "list"],
            capture_output=True,
            text=True,
        )
        labels = _launchctl_labels(proc.stdout)
        if WATCHDOG_LABEL not in labels:
            _fail(
                f"watchdog launchd agent '{WATCHDOG_LABEL}' not loaded — "
                "run scripts/install_scheduler.sh --with-watchdog or make promote-ops"
            )
        print(f"  ✓ watchdog launchd agent loaded ({WATCHDOG_LABEL})")

    elif sys.platform.startswith("linux"):
        proc = subprocess.run(
            ["systemctl", "is-enabled", WATCHDOG_TIMER],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0 or "enabled" not in proc.stdout:
            _fail(
                f"watchdog systemd timer '{WATCHDOG_TIMER}' not enabled — "
                "run scripts/install_scheduler.sh --with-watchdog or make promote-ops"
            )
        print(f"  ✓ watchdog systemd timer enabled ({WATCHDOG_TIMER})")

    else:
        print("  ! Unknown OS — skipping watchdog verification")


def check_watchdog_recovery_enabled(*, skip_alerts_check: bool) -> None:
    if skip_alerts_check:
        print("  ! watchdog recovery check skipped (CI mode)")
        return

    if not _watchdog_unit_has_recover_flag():
        _fail(
            "watchdog unit lacks LOBSTER_WATCHDOG_RECOVER=1 — "
            "reinstall watchdog via make promote-ops or make upgrade-host"
        )

    if sys.platform == "darwin":
        print("  ✓ watchdog launchd plist has LOBSTER_WATCHDOG_RECOVER=1")
    elif sys.platform.startswith("linux"):
        print("  ✓ watchdog systemd unit has LOBSTER_WATCHDOG_RECOVER=1")
    else:
        print("  ! Unknown OS — skipping watchdog recovery verification")


def check_watchdog_deep_recovery_enabled(*, skip_alerts_check: bool) -> None:
    if skip_alerts_check:
        print("  ! watchdog deep recovery check skipped (CI mode)")
        return

    if not _watchdog_unit_has_deep_recover_flag():
        _fail(
            "watchdog unit lacks LOBSTER_WATCHDOG_DEEP_RECOVER=1 — "
            "reinstall watchdog via make promote-ops or make upgrade-host"
        )

    if sys.platform == "darwin":
        print("  ✓ watchdog launchd plist has LOBSTER_WATCHDOG_DEEP_RECOVER=1")
    elif sys.platform.startswith("linux"):
        print("  ✓ watchdog systemd unit has LOBSTER_WATCHDOG_DEEP_RECOVER=1")
    else:
        print("  ! Unknown OS — skipping watchdog deep recovery verification")


def check_watchdog_redeploy_recovery_enabled(*, skip_alerts_check: bool) -> None:
    if skip_alerts_check:
        print("  ! watchdog redeploy recovery check skipped (CI mode)")
        return

    if not _watchdog_unit_has_redeploy_recover_flag():
        _fail(
            "watchdog unit lacks LOBSTER_WATCHDOG_REDEPLOY_RECOVER=1 — "
            "reinstall watchdog via make promote-ops or make upgrade-host"
        )

    if sys.platform == "darwin":
        print("  ✓ watchdog launchd plist has LOBSTER_WATCHDOG_REDEPLOY_RECOVER=1")
    elif sys.platform.startswith("linux"):
        print("  ✓ watchdog systemd unit has LOBSTER_WATCHDOG_REDEPLOY_RECOVER=1")
    else:
        print("  ! Unknown OS — skipping watchdog redeploy recovery verification")


def check_watchdog_rebuild_recovery_enabled(*, skip_alerts_check: bool) -> None:
    if skip_alerts_check:
        print("  ! watchdog rebuild recovery check skipped (CI mode)")
        return

    if not _watchdog_unit_has_rebuild_recover_flag():
        _fail(
            "watchdog unit lacks LOBSTER_WATCHDOG_REBUILD_RECOVER=1 — "
            "reinstall watchdog via make promote-ops or make upgrade-host"
        )

    if sys.platform == "darwin":
        print("  ✓ watchdog launchd plist has LOBSTER_WATCHDOG_REBUILD_RECOVER=1")
    elif sys.platform.startswith("linux"):
        print("  ✓ watchdog systemd unit has LOBSTER_WATCHDOG_REBUILD_RECOVER=1")
    else:
        print("  ! Unknown OS — skipping watchdog rebuild recovery verification")


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
        ("gate_c", lambda: check_gate_c(skip_scheduling=args.skip_scheduling)),
        ("ralph_learnings", lambda: check_ralph_learnings(ralph_path=args.ralph_path)),
        (
            "ops_scheduler_loaded",
            lambda: check_ops_scheduler_loaded(skip_alerts_check=args.skip_alerts_check),
        ),
        (
            "alerts_enabled",
            lambda: check_alerts_enabled(skip_alerts_check=args.skip_alerts_check),
        ),
        (
            "watchdog_loaded",
            lambda: check_watchdog_loaded(skip_alerts_check=args.skip_alerts_check),
        ),
        (
            "watchdog_recovery_enabled",
            lambda: check_watchdog_recovery_enabled(skip_alerts_check=args.skip_alerts_check),
        ),
        (
            "watchdog_deep_recovery_enabled",
            lambda: check_watchdog_deep_recovery_enabled(skip_alerts_check=args.skip_alerts_check),
        ),
        (
            "watchdog_redeploy_recovery_enabled",
            lambda: check_watchdog_redeploy_recovery_enabled(skip_alerts_check=args.skip_alerts_check),
        ),
        (
            "watchdog_rebuild_recovery_enabled",
            lambda: check_watchdog_rebuild_recovery_enabled(skip_alerts_check=args.skip_alerts_check),
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
