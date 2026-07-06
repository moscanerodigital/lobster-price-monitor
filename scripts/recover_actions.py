#!/usr/bin/env python3
"""Host recovery action planning from status_host JSON."""

from __future__ import annotations

import json
import sys
from typing import Any


def plan_recovery_actions(status: dict[str, Any]) -> list[str]:
    """Return ordered recovery action codes for a degraded host status."""
    if status.get("status") == "fatal":
        return []

    actions: list[str] = []
    units = status.get("units") or {}
    scrape = status.get("scrape") or {}
    health = status.get("health") or {}
    scheduler_mode = status.get("scheduler_mode", "none")

    if scheduler_mode not in ("dry-run", "ops"):
        return actions

    if not units.get("serve_loaded") or not units.get("serve_active"):
        actions.append("reload_serve")

    if not units.get("scrape_loaded") or not units.get("scrape_active"):
        actions.append("reload_scrape_scheduler")

    if scrape.get("stale"):
        if "trigger_scrape" not in actions:
            actions.append("trigger_scrape")

    health_status = health.get("status", "unknown")
    if health_status not in ("ready", "dry-run"):
        if "trigger_scrape" not in actions:
            actions.append("trigger_scrape")
        actions.append("rerun_health")

    if scheduler_mode == "ops" and not units.get("watchdog_loaded"):
        actions.append("install_watchdog")

    # Preserve order while deduping
    seen: set[str] = set()
    ordered: list[str] = []
    for action in actions:
        if action not in seen:
            seen.add(action)
            ordered.append(action)
    return ordered


def plan_deep_recovery_actions(
    status: dict[str, Any],
    *,
    tier1_ran: bool = False,
    still_degraded: bool = False,
) -> list[str]:
    """Return tier-2 recovery actions when basic remediation did not restore health."""
    if status.get("status") == "fatal":
        return []

    scheduler_mode = status.get("scheduler_mode", "none")
    if scheduler_mode not in ("dry-run", "ops"):
        return []

    if still_degraded or tier1_ran:
        return ["upgrade_host"]
    return []


def action_labels(action: str) -> str:
    labels = {
        "reload_serve": "reload serve unit",
        "reload_scrape_scheduler": "reload scrape scheduler",
        "trigger_scrape": "run confirmation scrape",
        "rerun_health": "re-run health_check.py",
        "install_watchdog": "install watchdog timer",
        "upgrade_host": "run upgrade_host (refresh deps + reload schedulers)",
    }
    return labels.get(action, action)


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: recover_actions.py <status-json>", file=sys.stderr)
        return 1
    status = json.loads(sys.argv[1])
    for action in plan_recovery_actions(status):
        print(action)
    return 0


if __name__ == "__main__":
    sys.exit(main())
