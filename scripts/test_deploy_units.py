"""Static deploy-unit regression tests (no host scheduler required)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LAUNCHD = ROOT / "deploy" / "launchd"
SYSTEMD = ROOT / "deploy" / "systemd"


def _read_label(plist_path: Path) -> str:
    text = plist_path.read_text(encoding="utf-8")
    match = re.search(
        r"<key>Label</key>\s*<string>([^<]+)</string>",
        text,
    )
    assert match, f"Label not found in {plist_path}"
    return match.group(1)


def _weekend_intervals(text: str) -> int:
    """Count StartCalendarInterval dicts with Weekday 0 (Sun) or 6 (Sat)."""
    return len(re.findall(r"<key>Weekday</key>\s*<integer>[06]</integer>", text))


def test_launchd_ops_label_differs_from_dry_run() -> None:
    dry = LAUNCHD / "com.erik.lobster-price-monitor.scrape.plist"
    ops = LAUNCHD / "com.erik.lobster-price-monitor.scrape.ops.plist"
    dry_label = _read_label(dry)
    ops_label = _read_label(ops)
    assert dry_label != ops_label, "ops and dry-run launchd labels must differ"
    assert ops_label == "com.erik.lobster-price-monitor.scrape.ops"


def test_launchd_plists_have_weekend_schedule() -> None:
    for name in (
        "com.erik.lobster-price-monitor.scrape.plist",
        "com.erik.lobster-price-monitor.scrape.ops.plist",
    ):
        text = (LAUNCHD / name).read_text(encoding="utf-8")
        count = _weekend_intervals(text)
        assert count >= 4, f"{name} should have 4 weekend intervals (Sat/Sun 9+17), got {count}"


def test_systemd_ops_timer_exists_and_references_ops_service() -> None:
    timer = SYSTEMD / "lobster-price-monitor-scrape.ops.timer"
    assert timer.exists(), "ops timer file missing"
    text = timer.read_text(encoding="utf-8")
    assert "lobster-price-monitor-scrape.ops.service" in text
    assert "OnCalendar=Sat,Sun 09:00" in text
    assert "OnCalendar=Sat,Sun 17:00" in text


def test_crontab_example_uses_run_scrape_sh() -> None:
    crontab = (ROOT / "deploy" / "crontab.example").read_text(encoding="utf-8")
    assert "scripts/run_scrape.sh" in crontab
    assert "LOBSTER_ALERTS=1" in crontab


def test_systemd_services_use_lobster_root_placeholder() -> None:
    stale = "/opt/lobster-price-monitor"
    for name in (
        "lobster-price-monitor-scrape.service",
        "lobster-price-monitor-scrape.ops.service",
        "lobster-price-monitor-serve.service",
    ):
        text = (SYSTEMD / name).read_text(encoding="utf-8")
        assert stale not in text, f"{name} still contains hardcoded install path"
        assert "LOBSTER_ROOT" in text, f"{name} should use LOBSTER_ROOT placeholder"


def test_systemd_timers_exist() -> None:
    for name in (
        "lobster-price-monitor-scrape.timer",
        "lobster-price-monitor-scrape.ops.timer",
        "lobster-price-monitor-health.timer",
        "lobster-price-monitor-watchdog.timer",
    ):
        assert (SYSTEMD / name).exists(), f"{name} missing"


def test_watchdog_units_exist() -> None:
    watchdog_plist = LAUNCHD / "com.erik.lobster-price-monitor.watchdog.plist"
    assert watchdog_plist.exists(), "watchdog launchd plist missing"
    text = watchdog_plist.read_text(encoding="utf-8")
    assert "watchdog_host.sh" in text
    assert "--notify" in text
    assert "LOBSTER_WATCHDOG_ALERTS" in text
    assert "LOBSTER_WATCHDOG_RECOVER" in text
    assert re.search(
        r"<key>LOBSTER_WATCHDOG_RECOVER</key>\s*<string>1</string>",
        text,
    )
    assert "LOBSTER_WATCHDOG_DEEP_RECOVER" in text
    assert re.search(
        r"<key>LOBSTER_WATCHDOG_DEEP_RECOVER</key>\s*<string>1</string>",
        text,
    )
    assert "LOBSTER_WATCHDOG_REDEPLOY_RECOVER" in text
    assert re.search(
        r"<key>LOBSTER_WATCHDOG_REDEPLOY_RECOVER</key>\s*<string>1</string>",
        text,
    )
    assert "LOBSTER_ROOT" in text

    watchdog_service = SYSTEMD / "lobster-price-monitor-watchdog.service"
    assert watchdog_service.exists(), "watchdog systemd service missing"
    svc_text = watchdog_service.read_text(encoding="utf-8")
    assert "LOBSTER_ROOT" in svc_text
    assert "LOBSTER_WATCHDOG_ALERTS=1" in svc_text
    assert "LOBSTER_WATCHDOG_RECOVER=1" in svc_text
    assert "LOBSTER_WATCHDOG_DEEP_RECOVER=1" in svc_text
    assert "LOBSTER_WATCHDOG_REDEPLOY_RECOVER=1" in svc_text
    assert "/opt/lobster-price-monitor" not in svc_text

    watchdog_timer = SYSTEMD / "lobster-price-monitor-watchdog.timer"
    assert watchdog_timer.exists(), "watchdog systemd timer missing"
    timer_text = watchdog_timer.read_text(encoding="utf-8")
    assert "10:00:00" in timer_text
    assert "22:00:00" in timer_text


def test_health_units_exist() -> None:
    health_plist = LAUNCHD / "com.erik.lobster-price-monitor.health.plist"
    assert health_plist.exists(), "health launchd plist missing"
    text = health_plist.read_text(encoding="utf-8")
    assert "health_check.py" in text
    assert "--log" in text
    assert "LOBSTER_ROOT" in text

    health_service = SYSTEMD / "lobster-price-monitor-health.service"
    assert health_service.exists(), "health systemd service missing"
    svc_text = health_service.read_text(encoding="utf-8")
    assert "LOBSTER_ROOT" in svc_text
    assert "/opt/lobster-price-monitor" not in svc_text


def main() -> int:
    tests = [
        test_launchd_ops_label_differs_from_dry_run,
        test_launchd_plists_have_weekend_schedule,
        test_systemd_ops_timer_exists_and_references_ops_service,
        test_systemd_services_use_lobster_root_placeholder,
        test_systemd_timers_exist,
        test_watchdog_units_exist,
        test_health_units_exist,
        test_crontab_example_uses_run_scrape_sh,
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
    print("\nAll deploy unit tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
