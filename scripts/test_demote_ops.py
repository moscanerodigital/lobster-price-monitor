"""Tests for scripts/demote_ops.sh."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "demote_ops.sh"


def test_demote_ops_dry_run_exits_zero() -> None:
    proc = subprocess.run(
        ["bash", str(SCRIPT), "--dry-run"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    assert "Ops demotion succeeded" in proc.stdout
    assert "verify-deploy" in proc.stdout


def test_demote_ops_dry_run_swaps_scheduler() -> None:
    import platform

    proc = subprocess.run(
        ["bash", str(SCRIPT), "--dry-run"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    if platform.system() == "Darwin":
        assert "launchctl unload" in proc.stdout or "[dry-run]" in proc.stdout
        assert "launchctl load" in proc.stdout or "scrape.plist" in proc.stdout
    else:
        assert "scrape.ops" in proc.stdout
        assert "scrape.timer" in proc.stdout


def test_demote_ops_fails_without_venv() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        fake_root = Path(td) / "fake"
        fake_root.mkdir()
        proc = subprocess.run(
            ["bash", str(SCRIPT), "--dry-run", "--lobster-root", str(fake_root)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
    assert proc.returncode == 1
    assert "venv not found" in proc.stderr or "venv not found" in proc.stdout


def main() -> int:
    tests = [
        test_demote_ops_dry_run_exits_zero,
        test_demote_ops_dry_run_swaps_scheduler,
        test_demote_ops_fails_without_venv,
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
    print("\nAll demote_ops tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
