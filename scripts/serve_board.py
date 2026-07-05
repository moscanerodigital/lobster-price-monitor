#!/usr/bin/env python3
"""Serve data/board.html on a stable localhost/LAN port."""
from __future__ import annotations

import argparse
import http.server
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from state import DATA_DIR


class BoardHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, directory: str | None = None, **kwargs):
        super().__init__(*args, directory=directory, **kwargs)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        sys.stderr.write("%s - %s\n" % (self.address_string(), format % args))


def _lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve seafood board HTML")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()

    data_dir = DATA_DIR.resolve()
    if not (data_dir / "board.html").exists():
        print(f"Missing {data_dir / 'board.html'} — run scrape first", file=sys.stderr)
        return 1

    handler = lambda *a, **kw: BoardHandler(*a, directory=str(data_dir), **kw)  # noqa: E731
    server = http.server.ThreadingHTTPServer((args.host, args.port), handler)
    lan = _lan_ip()
    print(f"Serving board at http://127.0.0.1:{args.port}/board.html")
    print(f"LAN: http://{lan}:{args.port}/board.html")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
