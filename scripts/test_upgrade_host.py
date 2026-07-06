"""Tests for scripts/upgrade_host.sh."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "upgrade_host.sh"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )


def test_upgrade_host_dry_run_exits_zero() -> None:
    proc = _run("--dry-run", "--skip-scrape", "--skip-verify")
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    assert "Host upgrade succeeded" in proc.stdout


def test_upgrade_host_dry_run_shows_pull_install_reload() -> None:
    proc = _run("--dry-run", "--skip-scrape", "--skip-verify")
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    assert "Pulling latest code" in proc.stdout
    assert "Refreshing dependencies" in proc.stdout
    assert "install.sh" in proc.stdout
    assert "Scheduler mode:" in proc.stdout


def test_upgrade_host_skip_pull_omits_git() -> None:
    proc = _run("--dry-run", "--skip-pull", "--skip-scrape", "--skip-verify")
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    assert "Skipping git pull" in proc.stdout
    assert "git -C" not in proc.stdout
    assert "pull --ff-only" not in proc.stdout


def test_upgrade_host_propagates_dry_run() -> None:
    proc = _run("--dry-run", "--skip-scrape", "--skip-verify")
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    assert "[dry-run]" in proc.stdout


def main() -> int:
    tests = [
        test_upgrade_host_dry_run_exits_zero,
        test_upgrade_host_dry_run_shows_pull_install_reload,
        test_upgrade_host_skip_pull_omits_git,
        test_upgrade_host_propagates_dry_run,
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
    print("\nAll upgrade_host tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
