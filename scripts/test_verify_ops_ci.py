"""Gate D ops CI fixture verification tests."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from refresh_ci_fixture_dates import refresh_bplus_fixtures
from test_verify_production_ci import _restore_project_data, _seed_project_data

ROOT = Path(__file__).resolve().parent.parent


def test_verify_ops_gate_passes_with_bplus_fixtures() -> None:
    with tempfile.TemporaryDirectory() as td:
        data_dir = Path(td)
        refresh_bplus_fixtures(dst=data_dir)
        backup = _seed_project_data(data_dir)
        ralph_backup = (ROOT / "RALPH.md").read_text(encoding="utf-8")
        try:
            proc_update = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "update_ralph_learnings.py")],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
            )
            assert proc_update.returncode == 0, proc_update.stderr

            proc = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "verify_ops_gate.py"),
                    "--skip-alerts-check",
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
            )
        finally:
            _restore_project_data(backup)
            (ROOT / "RALPH.md").write_text(ralph_backup, encoding="utf-8")

    assert proc.returncode == 0, f"verify_ops_gate failed:\n{proc.stdout}\n{proc.stderr}"
    assert "GATE D OPS VERIFICATION PASSED" in proc.stdout


def main() -> int:
    tests = [
        test_verify_ops_gate_passes_with_bplus_fixtures,
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
    print("\nAll Gate D CI tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
