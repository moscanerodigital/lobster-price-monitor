#!/usr/bin/env python3
"""Serve data/board.html on localhost, LAN, and Tailscale tailnet."""

from __future__ import annotations

import argparse
import http.server
import json
import os
import socket
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from state import DATA_DIR

ALLOWED_PATHS = frozenset({"/", "/board.html", "/index.html"})


class BoardHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, directory: str | None = None, **kwargs):
        super().__init__(*args, directory=directory, **kwargs)

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/":
            self.send_response(302)
            self.send_header("Location", "/board.html")
            self.end_headers()
            return
        if path not in ALLOWED_PATHS:
            self.send_error(403, "Forbidden")
            return
        if path == "/index.html":
            self.path = "/board.html"
        super().do_GET()

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


def _tailscale_info() -> tuple[str | None, str | None]:
    try:
        proc = subprocess.run(
            ["tailscale", "ip", "-4"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            return None, None
        ts_ip = proc.stdout.strip().splitlines()[0]
    except (OSError, subprocess.TimeoutExpired):
        return None, None

    ts_host: str | None = None
    try:
        status = subprocess.run(
            ["tailscale", "status", "--json"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        if status.returncode == 0 and status.stdout.strip():
            dns = json.loads(status.stdout).get("Self", {}).get("DNSName", "")
            ts_host = str(dns).rstrip(".") or None
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError, AttributeError):
        pass
    return ts_ip, ts_host


def _default_host() -> str:
    return os.environ.get("BIND") or os.environ.get("HOST") or "0.0.0.0"


def _default_port() -> int:
    raw = os.environ.get("PORT", "8765")
    try:
        return int(raw)
    except ValueError:
        return 8765


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve seafood board HTML")
    parser.add_argument("--port", type=int, default=_default_port())
    parser.add_argument("--host", "--bind", dest="host", default=_default_host())
    args = parser.parse_args()

    data_dir = DATA_DIR.resolve()
    if not (data_dir / "board.html").exists():
        print(f"Missing {data_dir / 'board.html'} — run scrape first", file=sys.stderr)
        return 1

    handler = lambda *a, **kw: BoardHandler(*a, directory=str(data_dir), **kw)  # noqa: E731
    server = http.server.ThreadingHTTPServer((args.host, args.port), handler)
    lan = _lan_ip()
    ts_ip, ts_host = _tailscale_info()
    print(f"Serving board at http://127.0.0.1:{args.port}/board.html")
    print(f"LAN: http://{lan}:{args.port}/board.html")
    if ts_ip:
        print(f"Tailnet: http://{ts_ip}:{args.port}/board.html")
    if ts_host:
        print(f"Tailnet (MagicDNS): http://{ts_host}:{args.port}/board.html")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
