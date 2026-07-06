"""Tests for scripts/teardown_host.sh."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "teardown_host.sh"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )


def test_teardown_host_dry_run_exits_zero() -> None:
    proc = _run("--dry-run")
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    assert "Host teardown succeeded" in proc.stdout


def test_teardown_host_dry_run_shows_demote_and_uninstall() -> None:
    proc = _run("--dry-run")
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    assert "Uninstalling all schedulers" in proc.stdout
    assert "uninstall_scheduler.sh" in proc.stdout or "scheduler uninstall" in proc.stdout


def test_teardown_host_skip_demote() -> None:
    proc = _run("--dry-run", "--skip-demote")
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    assert "Skipping ops demotion" in proc.stdout


def test_teardown_host_propagates_dry_run() -> None:
    proc = _run("--dry-run")
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    assert "[dry-run]" in proc.stdout


def main() -> int:
    tests = [
        test_teardown_host_dry_run_exits_zero,
        test_teardown_host_dry_run_shows_demote_and_uninstall,
        test_teardown_host_skip_demote,
        test_teardown_host_propagates_dry_run,
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
    print("\nAll teardown_host tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
