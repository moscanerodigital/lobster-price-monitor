"""Tests for scripts/host_health_state.py."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import state  # noqa: E402
from host_health_state import (  # noqa: E402
    consecutive_failures,
    escalation_threshold,
    record_outcome,
    should_escalate,
    watchdog_health_summary,
)

HOST_HEALTH_LOG = "host-health.jsonl"


def _backup_host_health() -> bytes | None:
    path = state.DATA_DIR / HOST_HEALTH_LOG
    if not path.exists():
        return None
    return path.read_bytes()


def _restore_host_health(backup: bytes | None) -> None:
    path = state.DATA_DIR / HOST_HEALTH_LOG
    if backup is None:
        path.unlink(missing_ok=True)
    else:
        path.write_bytes(backup)


def _seed_rows(rows: list[dict]) -> None:
    path = state.DATA_DIR / HOST_HEALTH_LOG
    state.DATA_DIR.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def test_consecutive_failures_counts_since_last_reset() -> None:
    backup = _backup_host_health()
    try:
        now = datetime.now(timezone.utc)
        _seed_rows(
            [
                {
                    "ts": (now - timedelta(hours=6)).isoformat(),
                    "outcome": "degraded",
                    "consecutive_failures": 1,
                },
                {
                    "ts": (now - timedelta(hours=3)).isoformat(),
                    "outcome": "degraded",
                    "consecutive_failures": 2,
                },
            ]
        )
        assert consecutive_failures() == 2
    finally:
        _restore_host_health(backup)


def test_consecutive_failures_resets_after_healthy() -> None:
    backup = _backup_host_health()
    try:
        now = datetime.now(timezone.utc)
        _seed_rows(
            [
                {
                    "ts": (now - timedelta(hours=6)).isoformat(),
                    "outcome": "degraded",
                    "consecutive_failures": 2,
                },
                {
                    "ts": (now - timedelta(hours=1)).isoformat(),
                    "outcome": "healthy",
                    "consecutive_failures": 0,
                },
            ]
        )
        assert consecutive_failures() == 0
    finally:
        _restore_host_health(backup)


def test_record_outcome_increments_streak() -> None:
    backup = _backup_host_health()
    try:
        _restore_host_health(None)
        streak = record_outcome(1, recovery_attempted=True)
        assert streak == 1
        streak = record_outcome(1, recovery_attempted=True)
        assert streak == 2
        streak = record_outcome(0, recovered=True)
        assert streak == 0
        assert consecutive_failures() == 0
    finally:
        _restore_host_health(backup)


def test_should_escalate_at_threshold() -> None:
    backup = _backup_host_health()
    try:
        _restore_host_health(None)
        threshold = escalation_threshold()
        for _ in range(threshold - 1):
            record_outcome(1)
        assert should_escalate() is False
        record_outcome(1)
        assert should_escalate() is True
    finally:
        _restore_host_health(backup)


def test_watchdog_health_summary_shape() -> None:
    backup = _backup_host_health()
    try:
        _restore_host_health(None)
        record_outcome(1)
        summary = watchdog_health_summary()
        assert summary["consecutive_failures"] == 1
        assert summary["escalation_threshold"] == escalation_threshold()
        assert summary["should_escalate"] is False
        assert summary["last_outcome"] == "degraded"
    finally:
        _restore_host_health(backup)


def test_host_health_state_cli_summary() -> None:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "host_health_state.py"), "--summary"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    assert "consecutive_failures" in data
    assert "escalation_threshold" in data


def main() -> int:
    tests = [
        test_consecutive_failures_counts_since_last_reset,
        test_consecutive_failures_resets_after_healthy,
        test_record_outcome_increments_streak,
        test_should_escalate_at_threshold,
        test_watchdog_health_summary_shape,
        test_host_health_state_cli_summary,
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
    print("\nAll host_health_state tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
