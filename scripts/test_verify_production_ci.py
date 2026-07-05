"""Gate C production CI fixture verification tests."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from refresh_ci_fixture_dates import refresh_bplus_fixtures

ROOT = Path(__file__).resolve().parent.parent


def _seed_project_data(data_dir: Path) -> dict[str, bytes]:
    """Copy fixture data into project data/ with backup/restore."""
    project_data = ROOT / "data"
    project_data.mkdir(parents=True, exist_ok=True)
    backup_files: dict[str, bytes] = {}
    for f in project_data.iterdir():
        if f.is_file():
            backup_files[f.name] = f.read_bytes()
            f.unlink()

    for f in data_dir.iterdir():
        if f.is_file():
            (project_data / f.name).write_bytes(f.read_bytes())
    return backup_files


def _restore_project_data(backup_files: dict[str, bytes]) -> None:
    project_data = ROOT / "data"
    for f in project_data.iterdir():
        if f.is_file():
            f.unlink()
    for name, content in backup_files.items():
        (project_data / name).write_bytes(content)


def test_verify_production_gate_passes_with_bplus_fixtures() -> None:
    with tempfile.TemporaryDirectory() as td:
        data_dir = Path(td)
        refresh_bplus_fixtures(dst=data_dir)
        backup = _seed_project_data(data_dir)
        try:
            proc = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "verify_production_gate.py"),
                    "--skip-scheduling",
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
            )
        finally:
            _restore_project_data(backup)

    assert proc.returncode == 0, (
        f"verify_production_gate failed:\n{proc.stdout}\n{proc.stderr}"
    )
    assert "GATE C PRODUCTION VERIFICATION PASSED" in proc.stdout


def main() -> int:
    tests = [
        test_verify_production_gate_passes_with_bplus_fixtures,
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
    print("\nAll Gate C CI tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
