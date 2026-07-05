"""Tests for update_ralph_learnings module."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import state
from update_ralph_learnings import (
    AUTO_HEADER,
    PLACEHOLDER,
    build_learnings_body,
    learnings_populated,
    update_learnings,
)

SAMPLE_RALPH = f"""# RALPH

## Learnings

{PLACEHOLDER}

## Usage / Budget Log

(empty)
"""

SAMPLE_RUN = {
    "ts": "2026-07-05T12:00:00+00:00",
    "markets_attempted": 9,
    "markets_succeeded": 8,
    "duration_seconds": 87.5,
    "avg_confidence": 81.8,
    "alerts_enabled": False,
    "alerts_suppressed": 2,
    "lobster_alerts": 0,
    "oyster_alerts": 0,
    "special_alerts": 0,
    "market_coverage": [
        {
            "market": "Five Islands Lobster Co.",
            "status": "partial",
            "blocker": "reference_menu:no_live_prices",
        }
    ],
    "errors": [],
}


def test_build_learnings_body_from_run_log() -> None:
    with tempfile.TemporaryDirectory() as td:
        data_dir = Path(td)
        run_log = data_dir / "run-log.jsonl"
        run_log.write_text(json.dumps(SAMPLE_RUN) + "\n", encoding="utf-8")
        with patch.object(state, "DATA_DIR", data_dir):
            body = build_learnings_body()
        assert AUTO_HEADER in body
        assert "8/9 markets" in body
        assert "Five Islands" in body


def test_update_learnings_writes_section() -> None:
    with tempfile.TemporaryDirectory() as td:
        data_dir = Path(td)
        ralph = Path(td) / "RALPH.md"
        ralph.write_text(SAMPLE_RALPH, encoding="utf-8")
        run_log = data_dir / "run-log.jsonl"
        run_log.write_text(json.dumps(SAMPLE_RUN) + "\n", encoding="utf-8")
        with patch.object(state, "DATA_DIR", data_dir):
            update_learnings(ralph_path=ralph)
            text = ralph.read_text(encoding="utf-8")
            assert learnings_populated(text)
            assert PLACEHOLDER not in text
            # Idempotent second run
            update_learnings(ralph_path=ralph)
            text2 = ralph.read_text(encoding="utf-8")
            assert learnings_populated(text2)


def main() -> int:
    tests = [
        test_build_learnings_body_from_run_log,
        test_update_learnings_writes_section,
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
    print("\nAll learnings tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
