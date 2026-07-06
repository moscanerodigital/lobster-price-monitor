"""B-05: scrape must publish board.html only after the full pipeline completes."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRAPE_PATH = ROOT / "scripts" / "scrape_markets.py"


def _main_function_source() -> ast.FunctionDef:
    tree = ast.parse(SCRAPE_PATH.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "main":
            return node
    raise AssertionError("main() not found in scrape_markets.py")


def test_write_html_board_only_after_run_log() -> None:
    """write_html_board must appear after append_jsonl('run-log.jsonl') in main()."""
    main_fn = _main_function_source()
    source = ast.get_source_segment(
        SCRAPE_PATH.read_text(encoding="utf-8"),
        main_fn,
    )
    assert source is not None
    run_log_idx = source.find('append_jsonl("run-log.jsonl"')
    board_idx = source.find("write_html_board()")
    assert run_log_idx >= 0, "append_jsonl run-log not found in main()"
    assert board_idx >= 0, "write_html_board() not found in main()"
    assert board_idx > run_log_idx, (
        "write_html_board() must run after append_jsonl('run-log.jsonl') "
        "to avoid publishing intermediate snapshots"
    )


def test_write_html_board_called_once_in_main() -> None:
    source = SCRAPE_PATH.read_text(encoding="utf-8")
    main_fn = _main_function_source()
    main_source = ast.get_source_segment(source, main_fn)
    assert main_source is not None
    assert main_source.count("write_html_board()") == 1


def main() -> int:
    tests = [
        test_write_html_board_only_after_run_log,
        test_write_html_board_called_once_in_main,
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
    print("\nAll scrape publish gate tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
