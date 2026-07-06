"""Tests for authenticated FB curl post discovery."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fb_curl_fetch import (
    FetchDiagnostics,
    _extract_post_texts,
    _page_post_acceptable,
    _page_urls,
    _post_is_seafood_menu,
)


def test_page_urls_prefer_mbasic() -> None:
    urls = _page_urls("TwoTidesSeafood")
    assert urls[0].startswith("https://mbasic.facebook.com/")


def test_extract_post_texts_from_embedded_json() -> None:
    html = '{"text":"Today\\u0027s catch menu:\\n• Scallops $24.99/lb\\n• Halibut $18.99/lb"}'
    texts = _extract_post_texts(html)
    assert len(texts) == 1
    assert "Scallops" in texts[0]


def test_seafood_menu_without_lobster_price() -> None:
    text = "Today's specials:\n• Scallops $24.99/lb\n• Gulf Haddock $11.99/lb"
    assert _post_is_seafood_menu(text) is True


def test_page_post_acceptable_menu_on_market_page() -> None:
    text = "Fresh catch today:\n• Scallops $24.99/lb\n• Halibut $18.99/lb"
    assert _page_post_acceptable(text, "Two Tides Seafood", "100054888565201") is True


def test_fetch_diagnostics_summary() -> None:
    diag = FetchDiagnostics(texts_found=3, texts_filtered=3)
    assert diag.summary() == "filtered"
    diag2 = FetchDiagnostics(http_errors=["http_403"])
    assert diag2.summary() == "http_403"


def main() -> int:
    tests = [
        test_page_urls_prefer_mbasic,
        test_extract_post_texts_from_embedded_json,
        test_seafood_menu_without_lobster_price,
        test_page_post_acceptable_menu_on_market_page,
        test_fetch_diagnostics_summary,
    ]
    failed = 0
    for test in tests:
        try:
            test()
            print(f"  ✓ {test.__name__}")
        except Exception as e:
            print(f"  ✗ {test.__name__}: {e}")
            failed += 1
    if failed:
        print(f"\n{failed} test(s) failed")
        return 1
    print("\nAll fb curl fetch tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
