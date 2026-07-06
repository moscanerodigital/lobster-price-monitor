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


def test_deploy_host_dry_run_teardown() -> None:
    proc = _run("--dry-run", "--teardown")
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    assert "Host teardown" in proc.stdout
    assert "teardown_host.sh" in proc.stdout or "scheduler uninstall" in proc.stdout
    assert "Phase 1: bootstrap" not in proc.stdout


def test_deploy_host_dry_run_teardown_purge_files() -> None:
    proc = _run("--dry-run", "--teardown", "--purge-files")
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    assert "--purge-files" in proc.stdout or "purge" in proc.stdout


def test_deploy_host_dry_run_upgrade() -> None:
    proc = _run("--dry-run", "--upgrade", "--skip-health")
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    assert "Host upgrade" in proc.stdout
    assert "upgrade_host.sh" in proc.stdout or "Pulling latest code" in proc.stdout
    assert "Phase 1: bootstrap" not in proc.stdout


def test_deploy_host_dry_run_status() -> None:
    proc = _run("--dry-run", "--status")
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    assert "Host status" in proc.stdout
    assert "status_host.sh" in proc.stdout or "Scheduler mode:" in proc.stdout
    assert "Phase 1: bootstrap" not in proc.stdout


def test_deploy_host_dry_run_watchdog() -> None:
    proc = _run("--dry-run", "--watchdog")
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    assert "Host watchdog" in proc.stdout
    assert "watchdog_host.sh" in proc.stdout or "Gate D Wave 12 host watchdog" in proc.stdout
    assert "Phase 1: bootstrap" not in proc.stdout


def test_deploy_host_dry_run_recover() -> None:
    proc = _run("--dry-run", "--recover")
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    assert "Host recovery" in proc.stdout
    assert "recover_host.sh" in proc.stdout or "Gate D Wave 12 host recovery" in proc.stdout
    assert "Phase 1: bootstrap" not in proc.stdout


def test_deploy_host_teardown_and_upgrade_mutually_exclusive() -> None:
    proc = _run("--teardown", "--upgrade")
    assert proc.returncode == 1
    assert "mutually exclusive" in proc.stderr.lower() or "mutually exclusive" in proc.stdout.lower()


def test_deploy_host_status_and_upgrade_mutually_exclusive() -> None:
    proc = _run("--status", "--upgrade")
    assert proc.returncode == 1
    assert "mutually exclusive" in proc.stderr.lower() or "mutually exclusive" in proc.stdout.lower()


def test_deploy_host_watchdog_and_status_mutually_exclusive() -> None:
    proc = _run("--watchdog", "--status")
    assert proc.returncode == 1
    assert "mutually exclusive" in proc.stderr.lower() or "mutually exclusive" in proc.stdout.lower()


def test_deploy_host_recover_and_status_mutually_exclusive() -> None:
    proc = _run("--recover", "--status")
    assert proc.returncode == 1
    assert "mutually exclusive" in proc.stderr.lower() or "mutually exclusive" in proc.stdout.lower()


def main() -> int:
    tests = [
        test_deploy_host_dry_run_phase1,
        test_deploy_host_dry_run_phase_all_without_promote_skips_phase3,
        test_deploy_host_dry_run_phase_all_with_promote_includes_phase3,
        test_deploy_host_dry_run_propagates_to_subscripts,
        test_deploy_host_invalid_phase,
        test_deploy_host_dry_run_teardown,
        test_deploy_host_dry_run_teardown_purge_files,
        test_deploy_host_dry_run_upgrade,
        test_deploy_host_dry_run_status,
        test_deploy_host_dry_run_watchdog,
        test_deploy_host_dry_run_recover,
        test_deploy_host_teardown_and_upgrade_mutually_exclusive,
        test_deploy_host_status_and_upgrade_mutually_exclusive,
        test_deploy_host_watchdog_and_status_mutually_exclusive,
        test_deploy_host_recover_and_status_mutually_exclusive,
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
