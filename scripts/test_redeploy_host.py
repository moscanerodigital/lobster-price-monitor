"""Tests for scripts/redeploy_host.sh."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "redeploy_host.sh"
DEPLOY_SCRIPT = ROOT / "scripts" / "deploy_host.sh"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )


def test_redeploy_host_dry_run_exits_zero() -> None:
    proc = _run("--dry-run", "--skip-scrape", "--skip-verify")
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    assert "Gate D Wave 13 host redeploy" in proc.stdout
    assert "Host redeploy succeeded" in proc.stdout


def test_redeploy_host_dry_run_shows_uninstall_reinstall() -> None:
    proc = _run("--dry-run", "--skip-scrape", "--skip-verify")
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    assert "Uninstalling schedulers" in proc.stdout
    assert "Reinstalling schedulers" in proc.stdout
    assert "scheduler uninstall" in proc.stdout.lower()
    assert "scheduler install" in proc.stdout.lower()


def test_redeploy_host_help() -> None:
    proc = _run("-h")
    assert proc.returncode == 0
    assert "redeploy_host.sh" in proc.stdout


def test_deploy_host_dry_run_redeploy() -> None:
    proc = subprocess.run(
        ["bash", str(DEPLOY_SCRIPT), "--dry-run", "--redeploy", "--skip-health"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    assert "Host redeploy" in proc.stdout
    assert "redeploy_host.sh" in proc.stdout or "Gate D Wave 13 host redeploy" in proc.stdout
    assert "Phase 1: bootstrap" not in proc.stdout


def main() -> int:
    tests = [
        test_redeploy_host_dry_run_exits_zero,
        test_redeploy_host_dry_run_shows_uninstall_reinstall,
        test_redeploy_host_help,
        test_deploy_host_dry_run_redeploy,
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
    print("\nAll redeploy_host tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
