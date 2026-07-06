#!/usr/bin/env python3
"""Host watchdog Telegram alerts — deduped infra health notifications."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import state
from send_alert import send_telegram

DEDUPE_HOURS = 6


def build_watchdog_reasons(status: dict) -> list[str]:
    """Human-readable reason lines from status_host JSON."""
    reasons: list[str] = []
    units = status.get("units") or {}
    scrape = status.get("scrape") or {}
    health = status.get("health") or {}
    scheduler_mode = status.get("scheduler_mode", "none")

    if status.get("status") == "fatal":
        reasons.append("fatal preflight error")

    if scrape.get("stale"):
        age = scrape.get("age_hours")
        if age is not None:
            reasons.append(f"scrape stale ({float(age):.1f}h)")
        else:
            reasons.append("scrape stale (>24h)")

    health_status = health.get("status", "unknown")
    if health_status not in ("ready", "dry-run"):
        reasons.append(f"health status: {health_status}")

    if scheduler_mode in ("dry-run", "ops"):
        if not units.get("scrape_loaded"):
            reasons.append("scrape scheduler not loaded")
        elif not units.get("scrape_active"):
            reasons.append("scrape unit not active")
        if not units.get("serve_loaded"):
            reasons.append("serve unit not loaded")
        elif not units.get("serve_active"):
            reasons.append("serve unit not active")

    if status.get("secrets_ok") is False:
        reasons.append("secrets preflight failed")

    if not reasons and status.get("status") in ("degraded", "fatal"):
        reasons.append("host status degraded")

    return reasons


def reason_codes(status: dict) -> list[str]:
    """Stable machine codes for dedupe hashing."""
    codes: list[str] = []
    units = status.get("units") or {}
    scrape = status.get("scrape") or {}
    health = status.get("health") or {}
    scheduler_mode = status.get("scheduler_mode", "none")

    if status.get("status") == "fatal":
        codes.append("fatal_preflight")
    if scrape.get("stale"):
        codes.append("scrape_stale")
    if health.get("status") not in ("ready", "dry-run", None):
        codes.append("health_degraded")
    if scheduler_mode in ("dry-run", "ops"):
        if not units.get("scrape_loaded"):
            codes.append("scrape_not_loaded")
        elif not units.get("scrape_active"):
            codes.append("scrape_not_active")
        if not units.get("serve_loaded"):
            codes.append("serve_not_loaded")
        elif not units.get("serve_active"):
            codes.append("serve_not_active")
    if status.get("secrets_ok") is False:
        codes.append("secrets_missing")
    if not codes:
        codes.append("host_degraded")
    return sorted(set(codes))


def reason_hash(status: dict) -> str:
    return "|".join(reason_codes(status))


def _recent_watchdog_alert(key: str, *, within_hours: int = DEDUPE_HOURS) -> bool:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=within_hours)
    for row in state.read_jsonl("alerts_sent.jsonl"):
        if row.get("kind") != "host_watchdog":
            continue
        if row.get("key") != key:
            continue
        ts = row.get("ts") or row.get("observed_at")
        if not ts:
            continue
        try:
            dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        except ValueError:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if dt.astimezone(timezone.utc) >= cutoff:
            return True
    return False


def _recent_recovery_alert(key: str, *, within_hours: int = DEDUPE_HOURS) -> bool:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=within_hours)
    for row in state.read_jsonl("alerts_sent.jsonl"):
        if row.get("kind") != "host_recovery":
            continue
        if row.get("key") != key:
            continue
        ts = row.get("ts") or row.get("observed_at")
        if not ts:
            continue
        try:
            dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        except ValueError:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if dt.astimezone(timezone.utc) >= cutoff:
            return True
    return False


def _recent_escalation_alert(key: str, *, within_hours: int = DEDUPE_HOURS) -> bool:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=within_hours)
    for row in state.read_jsonl("alerts_sent.jsonl"):
        if row.get("kind") != "host_escalation":
            continue
        if row.get("key") != key:
            continue
        ts = row.get("ts") or row.get("observed_at")
        if not ts:
            continue
        try:
            dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        except ValueError:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if dt.astimezone(timezone.utc) >= cutoff:
            return True
    return False


def alert_host_escalation(
    *,
    status: dict,
    exit_code: int,
    reasons: list[str],
    consecutive_failures: int,
    force: bool = False,
    dry_run: bool = False,
    recovery_attempted: bool = False,
    deep_recovery_attempted: bool = False,
    redeploy_recovery_attempted: bool = False,
) -> bool:
    """Send deduped escalation Telegram when failure streak meets threshold."""
    if not reasons:
        return False

    key = f"escalation|{reason_hash(status)}|streak={consecutive_failures}"
    if not force and _recent_escalation_alert(key):
        return False

    label = "FATAL" if exit_code >= 2 else "DEGRADED"
    lobster_root = status.get("lobster_root", "")
    git_rev = status.get("git_revision", "n/a")
    reason_lines = "\n".join(f"· {r}" for r in reasons)
    recovery_notes: list[str] = []
    if recovery_attempted:
        recovery_notes.append("auto-recovery attempted")
    if deep_recovery_attempted:
        recovery_notes.append("deep recovery attempted")
    if redeploy_recovery_attempted:
        recovery_notes.append("redeploy recovery attempted")
    recovery_note = ""
    if recovery_notes:
        recovery_note = "\n· " + " · ".join(recovery_notes)
    text = (
        f"🚨 *HOST ESCALATION* — lobster-price-monitor\n"
        f"status: {label} (exit {exit_code})\n"
        f"consecutive failures: {consecutive_failures}\n"
        f"{reason_lines}{recovery_note}\n"
        f"LOBSTER_ROOT: {lobster_root}\n"
        f"rev: {git_rev}\n"
        f"try: make upgrade-host · make redeploy-host · make recover-host · make demote-ops · make status-host"
    )

    if dry_run:
        print(f"[dry-run] would escalate: {key}")
        print(text)
        return True

    now = datetime.now(timezone.utc).isoformat()
    if send_telegram(text):
        state.append_jsonl(
            "alerts_sent.jsonl",
            {
                "key": key,
                "kind": "host_escalation",
                "exit_code": exit_code,
                "reasons": reasons,
                "reason_hash": reason_hash(status),
                "consecutive_failures": consecutive_failures,
                "lobster_root": lobster_root,
                "git_revision": git_rev,
                "ts": now,
                "observed_at": now,
            },
        )
        return True
    return False


def alert_host_recovery(
    *,
    status_before: dict,
    status_after: dict,
    actions_taken: list[str],
    exit_code_before: int,
    exit_code_after: int,
    force: bool = False,
    dry_run: bool = False,
) -> bool:
    """Send deduped Telegram summary of recovery attempt. Returns True if sent."""
    if not actions_taken:
        return False

    key = f"recovery|{reason_hash(status_before)}|{'|'.join(actions_taken)}"
    if not force and _recent_recovery_alert(key):
        return False

    label = "RECOVERED" if exit_code_after == 0 else "PARTIAL"
    lobster_root = status_after.get("lobster_root", status_before.get("lobster_root", ""))
    git_rev = status_after.get("git_revision", status_before.get("git_revision", "n/a"))
    action_lines = "\n".join(f"· {a}" for a in actions_taken)
    text = (
        f"🔧 *HOST RECOVERY* — lobster-price-monitor\n"
        f"before: exit {exit_code_before} → after: exit {exit_code_after} ({label})\n"
        f"{action_lines}\n"
        f"LOBSTER_ROOT: {lobster_root}\n"
        f"rev: {git_rev}\n"
        f"run: make status-host"
    )

    if dry_run:
        print(f"[dry-run] would alert recovery: {key}")
        print(text)
        return True

    now = datetime.now(timezone.utc).isoformat()
    if send_telegram(text):
        state.append_jsonl(
            "alerts_sent.jsonl",
            {
                "key": key,
                "kind": "host_recovery",
                "exit_code_before": exit_code_before,
                "exit_code_after": exit_code_after,
                "actions_taken": actions_taken,
                "lobster_root": lobster_root,
                "git_revision": git_rev,
                "ts": now,
                "observed_at": now,
            },
        )
        return True
    return False


def alert_host_watchdog(
    *,
    status: dict,
    exit_code: int,
    reasons: list[str],
    force: bool = False,
    dry_run: bool = False,
    recovery_attempted: bool = False,
    deep_recovery_attempted: bool = False,
    redeploy_recovery_attempted: bool = False,
) -> bool:
    """Send deduped host-health Telegram. Returns True if sent."""
    if not reasons:
        return False

    key = f"watchdog|{reason_hash(status)}"
    if not force and _recent_watchdog_alert(key):
        return False

    label = "FATAL" if exit_code >= 2 else "DEGRADED"
    lobster_root = status.get("lobster_root", "")
    git_rev = status.get("git_revision", "n/a")
    reason_lines = "\n".join(f"· {r}" for r in reasons)
    recovery_notes: list[str] = []
    if recovery_attempted:
        recovery_notes.append("auto-recovery attempted")
    if deep_recovery_attempted:
        recovery_notes.append("deep recovery attempted")
    if redeploy_recovery_attempted:
        recovery_notes.append("redeploy recovery attempted")
    recovery_note = ""
    if recovery_notes:
        recovery_note = "\n· " + " · ".join(recovery_notes)
    text = (
        f"⚠️ *HOST WATCHDOG* — lobster-price-monitor\n"
        f"status: {label} (exit {exit_code})\n"
        f"{reason_lines}{recovery_note}\n"
        f"LOBSTER_ROOT: {lobster_root}\n"
        f"rev: {git_rev}\n"
        f"run: make status-host"
    )

    if dry_run:
        print(f"[dry-run] would alert: {key}")
        print(text)
        return True

    now = datetime.now(timezone.utc).isoformat()
    if send_telegram(text):
        state.append_jsonl(
            "alerts_sent.jsonl",
            {
                "key": key,
                "kind": "host_watchdog",
                "exit_code": exit_code,
                "reasons": reasons,
                "reason_hash": reason_hash(status),
                "lobster_root": lobster_root,
                "git_revision": git_rev,
                "ts": now,
                "observed_at": now,
            },
        )
        return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Send host watchdog/recovery Telegram alerts")
    parser.add_argument("--status-json", required=True, help="JSON from status_host.sh (before recovery)")
    parser.add_argument("--exit-code", type=int, help="Exit code (watchdog mode)")
    parser.add_argument("--recovery", action="store_true", help="Send recovery summary instead of watchdog")
    parser.add_argument("--status-json-after", help="JSON after recovery (recovery mode)")
    parser.add_argument("--exit-code-before", type=int, help="Exit code before recovery")
    parser.add_argument("--exit-code-after", type=int, help="Exit code after recovery")
    parser.add_argument(
        "--actions-taken",
        nargs="*",
        default=[],
        help="Recovery actions performed",
    )
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--recovery-attempted",
        action="store_true",
        help="Note in alert that auto-recovery was attempted before notifying",
    )
    parser.add_argument("--escalation", action="store_true", help="Send escalation alert")
    parser.add_argument("--consecutive-failures", type=int, default=0)
    parser.add_argument(
        "--deep-recovery-attempted",
        action="store_true",
        help="Note in escalation alert that deep recovery was attempted",
    )
    parser.add_argument(
        "--redeploy-recovery-attempted",
        action="store_true",
        help="Note in alert that redeploy recovery was attempted",
    )
    args = parser.parse_args()

    if args.escalation:
        if args.exit_code is None:
            print("ERROR: --exit-code required for escalation alerts", file=sys.stderr)
            return 1
        status = json.loads(args.status_json)
        reasons = build_watchdog_reasons(status)
        if not reasons:
            return 0
        alert_host_escalation(
            status=status,
            exit_code=args.exit_code,
            reasons=reasons,
            consecutive_failures=args.consecutive_failures,
            force=args.force,
            dry_run=args.dry_run,
            recovery_attempted=args.recovery_attempted,
            deep_recovery_attempted=args.deep_recovery_attempted,
            redeploy_recovery_attempted=args.redeploy_recovery_attempted,
        )
        return 0

    if args.recovery:
        status_before = json.loads(args.status_json)
        status_after = json.loads(args.status_json_after or args.status_json)
        alert_host_recovery(
            status_before=status_before,
            status_after=status_after,
            actions_taken=list(args.actions_taken),
            exit_code_before=int(args.exit_code_before or 1),
            exit_code_after=int(args.exit_code_after or 0),
            force=args.force,
            dry_run=args.dry_run,
        )
        return 0

    if args.exit_code is None:
        print("ERROR: --exit-code required for watchdog alerts", file=sys.stderr)
        return 1

    status = json.loads(args.status_json)
    reasons = build_watchdog_reasons(status)
    if not reasons:
        return 0

    alert_host_watchdog(
        status=status,
        exit_code=args.exit_code,
        reasons=reasons,
        force=args.force,
        dry_run=args.dry_run,
        recovery_attempted=args.recovery_attempted,
        deep_recovery_attempted=args.deep_recovery_attempted,
        redeploy_recovery_attempted=args.redeploy_recovery_attempted,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
