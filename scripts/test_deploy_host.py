"""Tests for scripts/deploy_host.sh."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "deploy_host.sh"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )


def test_deploy_host_dry_run_phase1() -> None:
    proc = _run("--dry-run", "--phase", "1", "--skip-health")
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    assert "Phase 1: bootstrap" in proc.stdout
    assert "bootstrap_host.sh" in proc.stdout or "install.sh" in proc.stdout
    assert "Phase 2" not in proc.stdout


def test_deploy_host_dry_run_phase_all_without_promote_skips_phase3() -> None:
    proc = _run("--dry-run", "--phase", "all", "--skip-health")
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    assert "Phase 1: bootstrap" in proc.stdout
    assert "Phase 2: scheduler install" in proc.stdout
    assert "Phase 3: ops promotion" not in proc.stdout
    assert "--promote" in proc.stdout


def test_deploy_host_dry_run_phase_all_with_promote_includes_phase3() -> None:
    proc = _run("--dry-run", "--phase", "all", "--skip-health", "--promote")
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    assert "Phase 3: ops promotion" in proc.stdout
    assert "Ops promotion succeeded" in proc.stdout


def test_deploy_host_dry_run_propagates_to_subscripts() -> None:
    proc = _run("--dry-run", "--phase", "2", "--skip-health")
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    assert "[dry-run]" in proc.stdout


def test_deploy_host_invalid_phase() -> None:
    proc = _run("--phase", "9")
    assert proc.returncode == 1
    assert "invalid" in proc.stderr.lower() or "invalid" in proc.stdout.lower()


def main() -> int:
    tests = [
        test_deploy_host_dry_run_phase1,
        test_deploy_host_dry_run_phase_all_without_promote_skips_phase3,
        test_deploy_host_dry_run_phase_all_with_promote_includes_phase3,
        test_deploy_host_dry_run_propagates_to_subscripts,
        test_deploy_host_invalid_phase,
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
    print("\nAll deploy_host tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
