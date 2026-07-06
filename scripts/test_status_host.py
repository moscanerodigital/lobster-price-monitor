"""Tests for scripts/status_host.sh."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "status_host.sh"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )


def test_status_host_dry_run_exits_zero() -> None:
    proc = _run("--dry-run")
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    assert "Host status: HEALTHY" in proc.stdout or "dry-run" in proc.stdout


def test_status_host_dry_run_shows_sections() -> None:
    proc = _run("--dry-run")
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    assert "Scheduler mode:" in proc.stdout
    assert "LOBSTER_ROOT:" in proc.stdout
    assert "Health" in proc.stdout or "health" in proc.stdout.lower()


def test_status_host_json_flag() -> None:
    proc = _run("--json", "--dry-run")
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    data = json.loads(proc.stdout)
    assert data["dry_run"] is True
    assert "scheduler_mode" in data
    assert "serve" in data
    assert "units" in data
    assert "watchdog_loaded" in data["units"]
    assert "watchdog_recover_enabled" in data["units"]
    assert data["units"]["watchdog_recover_enabled"] is False
    assert "watchdog_redeploy_enabled" in data["units"]
    assert data["units"]["watchdog_redeploy_enabled"] is False
    assert "watchdog_rebuild_enabled" in data["units"]
    assert data["units"]["watchdog_rebuild_enabled"] is False
    assert "watchdog_reprovision_enabled" in data["units"]
    assert data["units"]["watchdog_reprovision_enabled"] is False
    assert "watchdog_health" in data
    assert data["watchdog_health"]["consecutive_failures"] == 0
    assert data["watchdog_health"]["escalation_threshold"] == 3


def test_status_host_help() -> None:
    proc = _run("-h")
    assert proc.returncode == 0
    assert "status_host.sh" in proc.stdout


def main() -> int:
    tests = [
        test_status_host_dry_run_exits_zero,
        test_status_host_dry_run_shows_sections,
        test_status_host_json_flag,
        test_status_host_help,
    ]
    failed = 0
    for test in tests:
        name = test.__name__
        try:
            test()
            print(f"  ✓ {name}")
        except Exception as e:
            print(f"  ✗ {name}: {e}")
            failed += 1

    if failed:
        print(f"\n{failed} test(s) failed")
        return 1
    print("\nAll status_host tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
