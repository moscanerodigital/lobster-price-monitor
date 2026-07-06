"""Tests for scripts/rebuild_host.sh."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "rebuild_host.sh"
DEPLOY_SCRIPT = ROOT / "scripts" / "deploy_host.sh"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )


def test_rebuild_host_dry_run_exits_zero() -> None:
    proc = _run("--dry-run", "--skip-scrape", "--skip-verify")
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    assert "Gate D Wave 14 host rebuild" in proc.stdout
    assert "Host rebuild succeeded" in proc.stdout


def test_rebuild_host_dry_run_shows_venv_rebuild_and_redeploy() -> None:
    proc = _run("--dry-run", "--skip-scrape", "--skip-verify")
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    assert "Rebuilding venv" in proc.stdout
    assert "Bootstrap verify path" in proc.stdout
    assert "Scheduler redeploy" in proc.stdout
    assert "redeploy_host.sh" in proc.stdout or "Host redeploy succeeded" in proc.stdout


def test_rebuild_host_help() -> None:
    proc = _run("-h")
    assert proc.returncode == 0
    assert "rebuild_host.sh" in proc.stdout


def test_deploy_host_dry_run_rebuild() -> None:
    proc = subprocess.run(
        ["bash", str(DEPLOY_SCRIPT), "--dry-run", "--rebuild", "--skip-health"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    assert "Host rebuild" in proc.stdout
    assert "rebuild_host.sh" in proc.stdout or "Gate D Wave 14 host rebuild" in proc.stdout
    assert "Phase 1: bootstrap" not in proc.stdout


def test_deploy_host_rebuild_and_upgrade_mutually_exclusive() -> None:
    proc = subprocess.run(
        ["bash", str(DEPLOY_SCRIPT), "--rebuild", "--upgrade"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0
    assert "mutually exclusive" in proc.stderr.lower() or "mutually exclusive" in proc.stdout.lower()


def main() -> int:
    tests = [
        test_rebuild_host_dry_run_exits_zero,
        test_rebuild_host_dry_run_shows_venv_rebuild_and_redeploy,
        test_rebuild_host_help,
        test_deploy_host_dry_run_rebuild,
        test_deploy_host_rebuild_and_upgrade_mutually_exclusive,
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
    print("\nAll rebuild_host tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
