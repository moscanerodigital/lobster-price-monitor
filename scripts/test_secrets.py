"""Tests for scripts/secrets.py — Facebook cookie loading."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import secrets


def test_load_fb_cookies_from_dict_file() -> None:
    with tempfile.TemporaryDirectory() as td:
        cookie_path = Path(td) / "facebook-cookies.json"
        cookie_path.write_text(
            json.dumps({"c_user": "12345", "xs": "abc123"}),
            encoding="utf-8",
        )
        with patch.object(secrets, "FB_COOKIES_FILE", cookie_path):
            jar = secrets.load_fb_cookies()
    assert jar == {"c_user": "12345", "xs": "abc123"}


def test_load_fb_cookies_from_browser_export_list() -> None:
    with tempfile.TemporaryDirectory() as td:
        cookie_path = Path(td) / "facebook-cookies.json"
        cookie_path.write_text(
            json.dumps(
                [
                    {"name": "c_user", "value": "999"},
                    {"name": "xs", "value": "token"},
                ]
            ),
            encoding="utf-8",
        )
        with patch.object(secrets, "FB_COOKIES_FILE", cookie_path):
            jar = secrets.load_fb_cookies()
    assert jar == {"c_user": "999", "xs": "token"}


def test_load_fb_cookies_missing_returns_none() -> None:
    with tempfile.TemporaryDirectory() as td:
        cookie_path = Path(td) / "missing.json"
        with patch.object(secrets, "FB_COOKIES_FILE", cookie_path):
            with patch("browser_cookie3.chrome", side_effect=ImportError("no chrome")):
                assert secrets.load_fb_cookies() is None


def test_fb_curl_fetch_uses_secrets_path() -> None:
    import fb_curl_fetch

    with patch("fb_curl_fetch.load_fb_cookies", return_value={"c_user": "1", "xs": "x"}) as mock:
        assert fb_curl_fetch._load_cookie_dict() == {"c_user": "1", "xs": "x"}
    mock.assert_called_once()


def main() -> int:
    tests = [
        test_load_fb_cookies_from_dict_file,
        test_load_fb_cookies_from_browser_export_list,
        test_load_fb_cookies_missing_returns_none,
        test_fb_curl_fetch_uses_secrets_path,
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
    print("\nAll secrets tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
