"""Tests for archive_board.py."""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import archive_board as archive_mod
import state


def test_archive_board_creates_manifest() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        board = tmp_path / "board.html"
        board.write_text("<html>test</html>", encoding="utf-8")
        (tmp_path / "prices.jsonl").write_text('{"gate_passed": true}\n', encoding="utf-8")
        old_data = state.DATA_DIR
        try:
            state.DATA_DIR = tmp_path
            out = archive_mod.archive_board(board_path=board)
        finally:
            state.DATA_DIR = old_data
        assert out is not None and out.is_file()
        manifest = tmp_path / "archive" / "manifest.jsonl"
        assert manifest.is_file()
        line = json.loads(manifest.read_text(encoding="utf-8").strip())
        assert line["gated_row_count"] == 1


def main() -> int:
    tests = [test_archive_board_creates_manifest]
    failed = 0
    for test in tests:
        try:
            test()
            print(f"  ✓ {test.__name__}")
        except Exception as e:
            print(f"  ✗ {test.__name__}: {e}")
            failed += 1
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
