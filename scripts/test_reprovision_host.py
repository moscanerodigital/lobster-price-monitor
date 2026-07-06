"""Tests for scripts/reprovision_host.sh."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "reprovision_host.sh"
DEPLOY_SCRIPT = ROOT / "scripts" / "deploy_host.sh"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )


def test_reprovision_host_dry_run_exits_zero() -> None:
    proc = _run("--dry-run", "--skip-scrape", "--skip-verify")
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    assert "Gate D Wave 15 host reprovision" in proc.stdout
    assert "Host reprovision succeeded" in proc.stdout


def test_reprovision_host_dry_run_shows_teardown_pull_rebuild_redeploy() -> None:
    proc = _run("--dry-run", "--skip-scrape", "--skip-verify")
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    assert "Full teardown with purge" in proc.stdout
    assert "teardown_host.sh" in proc.stdout or "purge" in proc.stdout
    assert "Pulling latest code" in proc.stdout or "git" in proc.stdout
    assert "Rebuilding venv" in proc.stdout
    assert "Bootstrap verify path" in proc.stdout
    assert "Scheduler redeploy" in proc.stdout
    assert "redeploy_host.sh" in proc.stdout or "Host redeploy succeeded" in proc.stdout


def test_reprovision_host_help() -> None:
    proc = _run("-h")
    assert proc.returncode == 0
    assert "reprovision_host.sh" in proc.stdout


def test_deploy_host_dry_run_reprovision() -> None:
    proc = subprocess.run(
        ["bash", str(DEPLOY_SCRIPT), "--dry-run", "--reprovision", "--skip-health"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    assert "Host reprovision" in proc.stdout
    assert "reprovision_host.sh" in proc.stdout or "Gate D Wave 15 host reprovision" in proc.stdout
    assert "Phase 1: bootstrap" not in proc.stdout


def test_deploy_host_reprovision_and_rebuild_mutually_exclusive() -> None:
    proc = subprocess.run(
        ["bash", str(DEPLOY_SCRIPT), "--reprovision", "--rebuild"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0
    assert "mutually exclusive" in proc.stderr.lower() or "mutually exclusive" in proc.stdout.lower()


def test_deploy_host_reprovision_and_upgrade_mutually_exclusive() -> None:
    proc = subprocess.run(
        ["bash", str(DEPLOY_SCRIPT), "--reprovision", "--upgrade"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0
    assert "mutually exclusive" in proc.stderr.lower() or "mutually exclusive" in proc.stdout.lower()


def main() -> int:
    tests = [
        test_reprovision_host_dry_run_exits_zero,
        test_reprovision_host_dry_run_shows_teardown_pull_rebuild_redeploy,
        test_reprovision_host_help,
        test_deploy_host_dry_run_reprovision,
        test_deploy_host_reprovision_and_rebuild_mutually_exclusive,
        test_deploy_host_reprovision_and_upgrade_mutually_exclusive,
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
    print("\nAll reprovision_host tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
