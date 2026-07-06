"""Tests for scripts/watchdog_host.sh and watchdog_alert.py."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "watchdog_host.sh"

sys.path.insert(0, str(ROOT / "scripts"))

from watchdog_alert import (  # noqa: E402
    alert_host_watchdog,
    build_watchdog_reasons,
    reason_hash,
)


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )


def test_watchdog_host_dry_run_exits_zero() -> None:
    proc = _run("--dry-run")
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    assert "Gate D Wave 9 host watchdog" in proc.stdout


def test_watchdog_host_dry_run_notify_would_alert() -> None:
    proc = _run("--dry-run", "--notify")
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    assert "would alert" in proc.stdout or "dry-run" in proc.stdout


def test_watchdog_host_help() -> None:
    proc = _run("-h")
    assert proc.returncode == 0
    assert "watchdog_host.sh" in proc.stdout
    assert "--recover" in proc.stdout


def test_watchdog_host_dry_run_recover() -> None:
    proc = _run("--dry-run", "--recover")
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    assert "recovery" in proc.stdout.lower()


def test_build_watchdog_reasons_stale_scrape() -> None:
    status = {
        "status": "degraded",
        "scheduler_mode": "ops",
        "scrape": {"stale": True, "age_hours": 28.3},
        "health": {"status": "ready"},
        "units": {
            "scrape_loaded": True,
            "scrape_active": True,
            "serve_loaded": True,
            "serve_active": True,
        },
        "secrets_ok": True,
    }
    reasons = build_watchdog_reasons(status)
    assert any("stale" in r for r in reasons)
    assert "scrape_stale" in reason_hash(status)


def test_alert_host_watchdog_dedupes_without_force() -> None:
    status = {
        "status": "degraded",
        "lobster_root": "/opt/lobster-price-monitor",
        "git_revision": "abc123",
        "scheduler_mode": "ops",
        "scrape": {"stale": True, "age_hours": 30.0},
        "health": {"status": "ready"},
        "units": {
            "scrape_loaded": True,
            "scrape_active": True,
            "serve_loaded": True,
            "serve_active": False,
        },
        "secrets_ok": True,
    }
    reasons = build_watchdog_reasons(status)

    with patch("watchdog_alert.send_telegram", return_value=True) as send_mock:
        with patch("watchdog_alert._recent_watchdog_alert", return_value=False):
            assert alert_host_watchdog(
                status=status,
                exit_code=1,
                reasons=reasons,
                dry_run=False,
            )
        send_mock.assert_called_once()

        with patch("watchdog_alert._recent_watchdog_alert", return_value=True):
            assert not alert_host_watchdog(
                status=status,
                exit_code=1,
                reasons=reasons,
                dry_run=False,
            )


def test_alert_host_watchdog_force_bypasses_dedupe() -> None:
    status = {
        "status": "degraded",
        "lobster_root": "/opt/lobster",
        "git_revision": "abc",
        "scheduler_mode": "none",
        "scrape": {"stale": False},
        "health": {"status": "degraded"},
        "units": {},
        "secrets_ok": True,
    }
    reasons = build_watchdog_reasons(status)

    with patch("watchdog_alert.send_telegram", return_value=True) as send_mock:
        with patch("watchdog_alert._recent_watchdog_alert", return_value=True):
            assert alert_host_watchdog(
                status=status,
                exit_code=1,
                reasons=reasons,
                force=True,
                dry_run=False,
            )
        send_mock.assert_called_once()


def test_watchdog_alert_cli_dry_run() -> None:
    status = {
        "status": "degraded",
        "lobster_root": "/opt/lobster",
        "git_revision": "abc",
        "scheduler_mode": "ops",
        "scrape": {"stale": True, "age_hours": 25.0},
        "health": {"status": "ready"},
        "units": {
            "scrape_loaded": True,
            "scrape_active": True,
            "serve_loaded": True,
            "serve_active": True,
        },
        "secrets_ok": True,
    }
    proc = subprocess.run(
        [
            str(ROOT / ".venv/bin/python"),
            str(ROOT / "scripts" / "watchdog_alert.py"),
            "--status-json",
            json.dumps(status),
            "--exit-code",
            "1",
            "--dry-run",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert "HOST WATCHDOG" in proc.stdout
    assert "stale" in proc.stdout.lower()


def main() -> int:
    tests = [
        test_watchdog_host_dry_run_exits_zero,
        test_watchdog_host_dry_run_notify_would_alert,
        test_watchdog_host_help,
        test_watchdog_host_dry_run_recover,
        test_build_watchdog_reasons_stale_scrape,
        test_alert_host_watchdog_dedupes_without_force,
        test_alert_host_watchdog_force_bypasses_dedupe,
        test_watchdog_alert_cli_dry_run,
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
    print("\nAll watchdog_host tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
