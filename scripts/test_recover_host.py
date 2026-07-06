"""Tests for scripts/recover_host.sh, recover_actions.py, and recovery alerts."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "recover_host.sh"
DEPLOY_SCRIPT = ROOT / "scripts" / "deploy_host.sh"
WATCHDOG_SCRIPT = ROOT / "scripts" / "watchdog_host.sh"

sys.path.insert(0, str(ROOT / "scripts"))

from recover_actions import action_labels, plan_recovery_actions  # noqa: E402
from watchdog_alert import alert_host_recovery  # noqa: E402


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )


def test_recover_host_dry_run_exits_zero() -> None:
    proc = _run("--dry-run")
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    assert "Gate D Wave 10 host recovery" in proc.stdout


def test_recover_host_help() -> None:
    proc = _run("-h")
    assert proc.returncode == 0
    assert "recover_host.sh" in proc.stdout


def test_plan_recovery_actions_stale_scrape() -> None:
    status = {
        "status": "degraded",
        "scheduler_mode": "dry-run",
        "scrape": {"stale": True, "age_hours": 30.0},
        "health": {"status": "ready"},
        "units": {
            "scrape_loaded": True,
            "scrape_active": True,
            "serve_loaded": True,
            "serve_active": True,
            "watchdog_loaded": False,
        },
    }
    actions = plan_recovery_actions(status)
    assert "trigger_scrape" in actions


def test_plan_recovery_actions_serve_not_active() -> None:
    status = {
        "status": "degraded",
        "scheduler_mode": "ops",
        "scrape": {"stale": False},
        "health": {"status": "ready"},
        "units": {
            "scrape_loaded": True,
            "scrape_active": True,
            "serve_loaded": True,
            "serve_active": False,
            "watchdog_loaded": True,
        },
    }
    actions = plan_recovery_actions(status)
    assert "reload_serve" in actions


def test_plan_recovery_actions_ops_missing_watchdog() -> None:
    status = {
        "status": "degraded",
        "scheduler_mode": "ops",
        "scrape": {"stale": False},
        "health": {"status": "ready"},
        "units": {
            "scrape_loaded": True,
            "scrape_active": True,
            "serve_loaded": True,
            "serve_active": True,
            "watchdog_loaded": False,
        },
    }
    actions = plan_recovery_actions(status)
    assert "install_watchdog" in actions


def test_action_labels_known_codes() -> None:
    assert action_labels("reload_serve") == "reload serve unit"
    assert action_labels("trigger_scrape") == "run confirmation scrape"


def test_alert_host_recovery_dry_run() -> None:
    before = {
        "status": "degraded",
        "lobster_root": "/opt/lobster",
        "git_revision": "abc",
        "scheduler_mode": "ops",
        "scrape": {"stale": True},
        "health": {"status": "ready"},
        "units": {"serve_active": True},
    }
    after = {
        "status": "healthy",
        "lobster_root": "/opt/lobster",
        "git_revision": "abc",
        "scheduler_mode": "ops",
        "scrape": {"stale": False},
        "health": {"status": "ready"},
        "units": {"serve_active": True},
    }
    with patch("watchdog_alert.send_telegram", return_value=True):
        assert alert_host_recovery(
            status_before=before,
            status_after=after,
            actions_taken=["run confirmation scrape"],
            exit_code_before=1,
            exit_code_after=0,
            dry_run=True,
        )


def test_deploy_host_dry_run_recover() -> None:
    proc = subprocess.run(
        ["bash", str(DEPLOY_SCRIPT), "--dry-run", "--recover"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    assert "Host recovery" in proc.stdout
    assert "recover_host.sh" in proc.stdout or "Gate D Wave 10 host recovery" in proc.stdout


def test_deploy_host_recover_and_watchdog_mutually_exclusive() -> None:
    proc = subprocess.run(
        ["bash", str(DEPLOY_SCRIPT), "--recover", "--watchdog"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    assert "mutually exclusive" in proc.stderr.lower() or "mutually exclusive" in proc.stdout.lower()


def test_watchdog_host_dry_run_recover_flag() -> None:
    proc = subprocess.run(
        ["bash", str(WATCHDOG_SCRIPT), "--dry-run", "--recover"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    assert "recovery" in proc.stdout.lower()


def main() -> int:
    tests = [
        test_recover_host_dry_run_exits_zero,
        test_recover_host_help,
        test_plan_recovery_actions_stale_scrape,
        test_plan_recovery_actions_serve_not_active,
        test_plan_recovery_actions_ops_missing_watchdog,
        test_action_labels_known_codes,
        test_alert_host_recovery_dry_run,
        test_deploy_host_dry_run_recover,
        test_deploy_host_recover_and_watchdog_mutually_exclusive,
        test_watchdog_host_dry_run_recover_flag,
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
    print("\nAll recover_host tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
