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


def main() -> int:
    tests = [
        test_launchd_ops_label_differs_from_dry_run,
        test_launchd_plists_have_weekend_schedule,
        test_systemd_ops_timer_exists_and_references_ops_service,
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
