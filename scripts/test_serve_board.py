"""Tests for serve_board.py security and cache headers."""

from __future__ import annotations

import socket
import sys
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from serve_board import BoardHandler  # noqa: E402
from state import DATA_DIR  # noqa: E402


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _start_server(port: int) -> ThreadingHTTPServer:
    data_dir = str(DATA_DIR.resolve())
    handler = lambda *a, **kw: BoardHandler(*a, directory=data_dir, **kw)  # noqa: E731
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def _fetch(url: str) -> tuple[int, dict[str, str], bytes]:
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:
            headers = {k.lower(): v for k, v in resp.headers.items()}
            return resp.status, headers, resp.read()
    except urllib.error.HTTPError as exc:
        headers = {k.lower(): v for k, v in exc.headers.items()}
        return exc.code, headers, exc.read()


def test_board_html_ok_with_no_cache() -> None:
    board = DATA_DIR / "board.html"
    assert board.is_file(), "data/board.html required for serve tests"
    port = _free_port()
    server = _start_server(port)
    try:
        status, headers, _body = _fetch(f"http://127.0.0.1:{port}/board.html")
        assert status == 200
        assert "no-cache" in headers.get("cache-control", "").lower()
        assert headers.get("x-content-type-options") == "nosniff"
    finally:
        server.shutdown()


def test_prices_jsonl_forbidden() -> None:
    prices = DATA_DIR / "prices.jsonl"
    if not prices.is_file():
        return
    port = _free_port()
    server = _start_server(port)
    try:
        status, _headers, _body = _fetch(f"http://127.0.0.1:{port}/prices.jsonl")
        assert status == 403
    finally:
        server.shutdown()


def test_root_redirects_to_board() -> None:
    board = DATA_DIR / "board.html"
    assert board.is_file()
    port = _free_port()
    server = _start_server(port)
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/", method="GET")
        try:
            urllib.request.urlopen(req, timeout=3)
        except urllib.error.HTTPError as exc:
            assert exc.code == 302
            location = exc.headers.get("Location", "")
            assert location.startswith("/board.html")
    finally:
        server.shutdown()


def main() -> int:
    tests = [
        test_board_html_ok_with_no_cache,
        test_prices_jsonl_forbidden,
        test_root_redirects_to_board,
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
    print("\nAll serve board tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
