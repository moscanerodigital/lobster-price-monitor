"""Tests for scripts/uninstall_scheduler.sh."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "uninstall_scheduler.sh"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )


def test_uninstall_scheduler_dry_run_exits_zero() -> None:
    proc = _run("--dry-run")
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    assert "Scheduler uninstall succeeded" in proc.stdout
    assert "[dry-run]" in proc.stdout


def test_uninstall_scheduler_dry_run_mentions_all_unit_families() -> None:
    proc = _run("--dry-run")
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    combined = proc.stdout + proc.stderr
    assert "scrape.ops" in combined
    assert "scrape" in combined
    assert "serve" in combined
    assert "health" in combined


def test_uninstall_scheduler_skip_health_omits_health_unit() -> None:
    proc = _run("--dry-run", "--skip-health")
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    assert "skipping health" in proc.stdout.lower()


def test_uninstall_scheduler_invalid_flag() -> None:
    proc = _run("--not-a-flag")
    assert proc.returncode == 1
    assert "Unknown option" in proc.stderr or "Unknown option" in proc.stdout


def main() -> int:
    tests = [
        test_uninstall_scheduler_dry_run_exits_zero,
        test_uninstall_scheduler_dry_run_mentions_all_unit_families,
        test_uninstall_scheduler_skip_health_omits_health_unit,
        test_uninstall_scheduler_invalid_flag,
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
    print("\nAll uninstall_scheduler tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
