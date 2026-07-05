"""Gate B+ CI fixture verification tests."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import state
from board_render import build_board
from refresh_ci_fixture_dates import _parse_iso, refresh_bplus_fixtures

ROOT = Path(__file__).resolve().parent.parent


def test_bplus_fixtures_seed_and_board_coverage() -> None:
    with tempfile.TemporaryDirectory() as td:
        data_dir = Path(td)
        with patch.object(state, "DATA_DIR", data_dir):
            refresh_bplus_fixtures(dst=data_dir)
            board = build_board()

        lobster = board.get("sections", {}).get("lobster", [])
        markets_on_board = {item.get("market", "") for item in lobster if item.get("market")}
        assert len(markets_on_board) >= 7, (
            f"expected ≥7 lobster markets on board, got {markets_on_board}"
        )

        coverage = {c["name"]: c for c in board.get("market_coverage", [])}
        five = coverage.get("Five Islands Lobster Co.", {})
        assert five.get("status") in ("partial", "blocked"), (
            f"Five Islands should be partial/blocked: {five}"
        )

        trends = board.get("trends", {})
        assert trends.get("labels"), "trends chart should have date labels"
        assert any(v is not None for v in trends.get("soft_shell", [])), (
            "soft_shell trend data expected"
        )
        assert any(v is not None for v in trends.get("hard_shell", [])), (
            "hard_shell trend data expected"
        )


def test_refresh_shifts_timestamps_forward() -> None:
    with tempfile.TemporaryDirectory() as td:
        dst = Path(td)
        refresh_bplus_fixtures(dst=dst)
        run = json.loads((dst / "run-log.jsonl").read_text(encoding="utf-8").strip().split("\n")[0])
        ts = _parse_iso(run["ts"])
        assert ts is not None
        age_hours = (datetime.now(timezone.utc) - ts).total_seconds() / 3600
        assert age_hours < 1.0, f"run-log ts should be fresh, age={age_hours:.2f}h"


def test_verify_next_gate_passes_with_bplus_fixtures() -> None:
    with tempfile.TemporaryDirectory() as td:
        data_dir = Path(td)
        refresh_bplus_fixtures(dst=data_dir)

        project_data = ROOT / "data"
        backup_files: dict[str, bytes] = {}
        for f in project_data.iterdir():
            if f.is_file():
                backup_files[f.name] = f.read_bytes()
                f.unlink()

        try:
            for f in data_dir.iterdir():
                if f.is_file():
                    (project_data / f.name).write_bytes(f.read_bytes())

            proc = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "verify_next_gate.py"),
                    "--min-lobster-markets",
                    "7",
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
            )
        finally:
            for f in project_data.iterdir():
                if f.is_file():
                    f.unlink()
            for name, content in backup_files.items():
                (project_data / name).write_bytes(content)

    assert proc.returncode == 0, f"verify_next_gate failed:\n{proc.stdout}\n{proc.stderr}"
    assert "GATE B+ PASSED" in proc.stdout


def main() -> int:
    tests = [
        test_refresh_shifts_timestamps_forward,
        test_bplus_fixtures_seed_and_board_coverage,
        test_verify_next_gate_passes_with_bplus_fixtures,
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
    print("\nAll B+ CI tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
