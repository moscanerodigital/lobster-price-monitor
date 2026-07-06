#!/usr/bin/env python3
"""Host watchdog failure tracking for recovery escalation."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

import state

HOST_HEALTH_LOG = "host-health.jsonl"
RESET_OUTCOMES = frozenset({"healthy", "recovered"})
FAILURE_OUTCOMES = frozenset({"degraded", "escalated", "fatal"})
DEFAULT_ESCALATE_AFTER = 3
DEFAULT_WITHIN_HOURS = 48


def escalation_threshold() -> int:
    raw = os.environ.get("LOBSTER_WATCHDOG_ESCALATE_AFTER", str(DEFAULT_ESCALATE_AFTER))
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_ESCALATE_AFTER


def _parse_ts(row: dict[str, Any]) -> datetime | None:
    ts = row.get("ts") or row.get("observed_at")
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _rows_within_hours(within_hours: int = DEFAULT_WITHIN_HOURS) -> list[dict[str, Any]]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=within_hours)
    rows: list[dict[str, Any]] = []
    for row in state.read_jsonl(HOST_HEALTH_LOG):
        dt = _parse_ts(row)
        if dt is None or dt < cutoff:
            continue
        rows.append(row)
    return rows


def consecutive_failures(*, within_hours: int = DEFAULT_WITHIN_HOURS) -> int:
    """Count consecutive failure outcomes since the last healthy/recovered row."""
    count = 0
    for row in reversed(_rows_within_hours(within_hours)):
        outcome = row.get("outcome", "")
        if outcome in RESET_OUTCOMES:
            break
        if outcome in FAILURE_OUTCOMES:
            count += 1
    return count


def last_outcome(*, within_hours: int = DEFAULT_WITHIN_HOURS) -> str | None:
    rows = _rows_within_hours(within_hours)
    if not rows:
        return None
    return str(rows[-1].get("outcome", "")) or None


def should_escalate(*, threshold: int | None = None, within_hours: int = DEFAULT_WITHIN_HOURS) -> bool:
    threshold = threshold if threshold is not None else escalation_threshold()
    return consecutive_failures(within_hours=within_hours) >= threshold


def watchdog_health_summary(*, within_hours: int = DEFAULT_WITHIN_HOURS) -> dict[str, Any]:
    threshold = escalation_threshold()
    streak = consecutive_failures(within_hours=within_hours)
    return {
        "consecutive_failures": streak,
        "escalation_threshold": threshold,
        "should_escalate": streak >= threshold,
        "last_outcome": last_outcome(within_hours=within_hours),
    }


def record_outcome(
    exit_code: int,
    *,
    recovery_attempted: bool = False,
    deep_recovery_attempted: bool = False,
    redeploy_recovery_attempted: bool = False,
    rebuild_recovery_attempted: bool = False,
    reprovision_recovery_attempted: bool = False,
    recovered: bool = False,
    escalated: bool = False,
) -> int:
    """Append a watchdog outcome row and return the new consecutive-failure count."""
    if exit_code == 0:
        outcome = "healthy"
    elif recovered:
        outcome = "recovered"
    elif escalated:
        outcome = "escalated"
    elif exit_code >= 2:
        outcome = "fatal"
    else:
        outcome = "degraded"

    prev_streak = consecutive_failures()
    if outcome in RESET_OUTCOMES:
        new_streak = 0
    else:
        new_streak = prev_streak + 1

    now = datetime.now(timezone.utc).isoformat()
    state.append_jsonl(
        HOST_HEALTH_LOG,
        {
            "ts": now,
            "observed_at": now,
            "outcome": outcome,
            "exit_code": exit_code,
            "recovery_attempted": recovery_attempted,
            "deep_recovery_attempted": deep_recovery_attempted,
            "redeploy_recovery_attempted": redeploy_recovery_attempted,
            "rebuild_recovery_attempted": rebuild_recovery_attempted,
            "reprovision_recovery_attempted": reprovision_recovery_attempted,
            "consecutive_failures": new_streak,
        },
    )
    return new_streak


def main() -> int:
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Host watchdog failure state")
    parser.add_argument("--summary", action="store_true", help="Print watchdog_health JSON")
    parser.add_argument("--record", action="store_true", help="Record an outcome row")
    parser.add_argument("--exit-code", type=int, default=0)
    parser.add_argument("--recovery-attempted", action="store_true")
    parser.add_argument("--deep-recovery-attempted", action="store_true")
    parser.add_argument("--redeploy-recovery-attempted", action="store_true")
    parser.add_argument("--rebuild-recovery-attempted", action="store_true")
    parser.add_argument("--reprovision-recovery-attempted", action="store_true")
    parser.add_argument("--recovered", action="store_true")
    parser.add_argument("--escalated", action="store_true")
    args = parser.parse_args()

    if args.record:
        streak = record_outcome(
            args.exit_code,
            recovery_attempted=args.recovery_attempted,
            deep_recovery_attempted=args.deep_recovery_attempted,
            redeploy_recovery_attempted=args.redeploy_recovery_attempted,
            rebuild_recovery_attempted=args.rebuild_recovery_attempted,
            reprovision_recovery_attempted=args.reprovision_recovery_attempted,
            recovered=args.recovered,
            escalated=args.escalated,
        )
        print(streak)
        return 0

    print(json.dumps(watchdog_health_summary(), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
