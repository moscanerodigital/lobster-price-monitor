"""C-03: structural visual QA for chalk board HTML (no Playwright)."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from board_render import build_board, render_html


def _board_html() -> str:
    board_path = ROOT / "data" / "board.html"
    if board_path.is_file():
        return board_path.read_text(encoding="utf-8")
    return render_html(build_board())


def test_no_cryptic_lob_crab_label() -> None:
    html = _board_html()
    assert "Lob/crab" not in html


def test_no_oyster_ea_per_dozen_mismatch() -> None:
    html = _board_html()
    row_pattern = re.compile(
        r'<li class="price-row section-oyster">(.*?)</li>',
        re.DOTALL | re.IGNORECASE,
    )
    for match in row_pattern.finditer(html):
        row = match.group(1)
        unit_match = re.search(
            r'<span class="price-unit">([^<]*)</span>',
            row,
            re.IGNORECASE,
        )
        secondary_match = re.search(
            r'<span class="row-secondary">([^<]*)</span>',
            row,
            re.IGNORECASE,
        )
        if not unit_match or not secondary_match:
            continue
        unit = unit_match.group(1).strip().lower()
        secondary = secondary_match.group(1).strip().lower()
        if unit in {"/ea", "ea", "each"} and "per dozen" in secondary:
            raise AssertionError(f"ea oyster row shows per dozen secondary: {secondary!r}")


def test_market_groups_no_nested_scroll() -> None:
    html = _board_html()
    for block in re.findall(r"\.market-groups\s*\{[^}]+\}", html, re.IGNORECASE):
        assert "overflow-y" not in block.lower() or "auto" not in block.lower(), (
            f"nested scroll on market-groups: {block}"
        )


def test_desktop_logo_size_at_least_80px() -> None:
    html = _board_html()
    assert re.search(
        r"--logo-size:\s*clamp\(\s*5rem",
        html,
        re.IGNORECASE,
    ), "desktop logo clamp should start at 5rem (80px)"


def test_board_has_three_sections() -> None:
    html = _board_html()
    for section in ("lobster", "oyster", "special"):
        assert f"section-{section}" in html


def test_lobster_grouped_label_strips_duplicate_prices() -> None:
    from chalk_board_html import _lobster_grouped_label

    item = {"row_secondary": "soft $10.49 · hard $10.99", "label": "Lobster"}
    assert _lobster_grouped_label(item) == "soft · hard"
    item2 = {"row_secondary": "1⅛ lb · hard $7.99", "label": "Lobster"}
    assert _lobster_grouped_label(item2) == "1⅛ lb · hard"


def test_no_duplicate_dollar_in_grouped_lobster_rows() -> None:
    html = _board_html()
    rows = re.findall(
        r'<li class="price-row section-lobster is-consolidated">(.*?)</li>',
        html,
        re.DOTALL | re.IGNORECASE,
    )
    assert rows, "expected consolidated lobster rows"
    for row in rows:
        primary = re.search(r'<span class="row-primary">([^<]*)</span>', row)
        assert primary, "missing row-primary"
        assert "$" not in primary.group(1), f"duplicate price in label: {primary.group(1)!r}"


def test_no_broken_trends_with_single_point() -> None:
    html = _board_html()
    if 'id="trendsChart"' in html:
        labels = re.findall(r'"labels":\s*\[([^\]]*)\]', html)
        for block in labels:
            count = len([p for p in block.split(",") if p.strip()])
            assert count >= 2, f"trends chart should have 2+ points, got {count}"


def test_no_chowder_lb_unit_mismatch() -> None:
    html = _board_html()
    assert "Chowder $9.99/pint" not in html
    assert "Haddock Chowder</span>" in html or "Haddock Chowder<span" in html
    chowder_rows = [
        m.group(0)
        for m in re.finditer(
            r'<li class="price-row section-special">.*?</li>',
            html,
            re.DOTALL | re.IGNORECASE,
        )
        if "chowder" in m.group(0).lower()
    ]
    for row in chowder_rows:
        if "/lb" in row.lower() and "chowder" in row.lower():
            raise AssertionError(f"chowder row shows /lb: {row[:200]}")


def test_live_section_minimums() -> None:
    if not os.environ.get("BOARD_QA_LIVE"):
        return
    board = build_board()
    assert len(board["sections"]["lobster"]) >= 8
    assert len(board["sections"]["oyster"]) >= 5
    assert len(board["sections"]["special"]) >= 25


def main() -> int:
    tests = [
        test_no_cryptic_lob_crab_label,
        test_no_oyster_ea_per_dozen_mismatch,
        test_market_groups_no_nested_scroll,
        test_desktop_logo_size_at_least_80px,
        test_board_has_three_sections,
        test_lobster_grouped_label_strips_duplicate_prices,
        test_no_duplicate_dollar_in_grouped_lobster_rows,
        test_no_broken_trends_with_single_point,
        test_no_chowder_lb_unit_mismatch,
        test_live_section_minimums,
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
    print("\nAll board visual tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
