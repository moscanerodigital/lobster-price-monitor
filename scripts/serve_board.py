#!/usr/bin/env python3
"""Serve data/board.html on localhost, LAN, and Tailscale tailnet."""

from __future__ import annotations

import argparse
import http.server
import json
import mimetypes
import os
import re
import socket
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from board_meta import cache_bust_token
from market_logos import LOGOS_DIR, MARKET_LOGO_SLUGS, logo_path_for_short
from state import DATA_DIR

BASE_ALLOWED_PATHS = frozenset({"/", "/board.html", "/index.html"})
_IMG_PREFIX = "/img/"


def _external_logos_enabled() -> bool:
    return os.environ.get("BOARD_EXTERNAL_LOGOS", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def _allowed_paths() -> frozenset[str]:
    if not _external_logos_enabled():
        return BASE_ALLOWED_PATHS
    extra = set()
    for short in MARKET_LOGO_SLUGS:
        rel = _logo_request_path(short)
        if rel:
            extra.add(rel)
    return BASE_ALLOWED_PATHS | frozenset(extra)


def _logo_request_path(market_short: str) -> str | None:
    path = logo_path_for_short(market_short)
    if path is None:
        return None
    slug = MARKET_LOGO_SLUGS.get(market_short)
    if not slug:
        return None
    return f"{_IMG_PREFIX}{slug}{path.suffix.lower() or '.webp'}"


def _board_cache_token() -> str:
    board_path = DATA_DIR / "board.html"
    if not board_path.is_file():
        return ""
    text = board_path.read_text(encoding="utf-8", errors="replace")
    match = re.search(r"generated\s+(\d{4}-\d{2}-\d{2}T[\d:+Z]+)", text)
    if match:
        return cache_bust_token(match.group(1))
    return cache_bust_token("")


class BoardHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, directory: str | None = None, **kwargs):
        super().__init__(*args, directory=directory, **kwargs)

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/":
            token = _board_cache_token()
            location = "/board.html"
            if token:
                location = f"/board.html?v={token}"
            self.send_response(302)
            self.send_header("Location", location)
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            return
        if path not in _allowed_paths():
            self.send_error(403, "Forbidden")
            return
        if path == "/index.html":
            self.path = "/board.html"
        if path.startswith(_IMG_PREFIX) and _external_logos_enabled():
            self._serve_logo(path)
            return
        super().do_GET()

    def _serve_logo(self, path: str) -> None:
        name = path[len(_IMG_PREFIX) :]
        file_path = LOGOS_DIR / name
        if not file_path.is_file():
            self.send_error(404, "Not found")
            return
        data = file_path.read_bytes()
        ctype = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "public, max-age=86400")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def end_headers(self) -> None:
        path = self.path.split("?", 1)[0]
        if path in {"/board.html", "/index.html"}:
            self.send_header("Cache-Control", "no-cache")
            self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()

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
    print(f"Serving board from {data_dir} (only board.html + allowlisted paths)")
    print(f"Serving board at http://127.0.0.1:{args.port}/board.html")
    print(f"LAN: http://{lan}:{args.port}/board.html")
    if ts_ip:
        print(f"Tailnet: http://{ts_ip}:{args.port}/board.html")
    if ts_host:
        print(f"Tailnet (MagicDNS): http://{ts_host}:{args.port}/board.html")
    if _external_logos_enabled():
        print("External logos: /img/*.webp enabled (BOARD_EXTERNAL_LOGOS=1)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
