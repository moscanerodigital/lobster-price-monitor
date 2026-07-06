"""Tests for scripts/bootstrap_host.sh."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "bootstrap_host.sh"


def test_bootstrap_dry_run_lists_phase1_steps() -> None:
    proc = subprocess.run(
        ["bash", str(SCRIPT), "--dry-run", "--skip-serve-smoke"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    out = proc.stdout
    for needle in (
        "Phase 1 host bootstrap",
        "scripts/install.sh",
        "scripts/dry_run.sh",
        "make -C",
        "verify",
        "health_check.py",
        "Phase 1 bootstrap succeeded",
    ):
        assert needle in out, f"missing {needle!r} in:\n{out}"


def test_bootstrap_fails_without_writable_lobster_root() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "readonly"
        root.mkdir()
        root.chmod(0o555)
        proc = subprocess.run(
            ["bash", str(SCRIPT), "--dry-run", "--lobster-root", str(root)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
    assert proc.returncode == 1
    assert "not writable" in proc.stderr or "not writable" in proc.stdout


def main() -> int:
    tests = [
        test_bootstrap_dry_run_lists_phase1_steps,
        test_bootstrap_fails_without_writable_lobster_root,
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
    print("\nAll bootstrap_host tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
