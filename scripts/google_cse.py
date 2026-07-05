"""Google Custom Search JSON API client — fallback for FB-blocked markets."""

from __future__ import annotations

import hashlib
import json
import os
import urllib.parse
import urllib.request
from pathlib import Path

from search_queries import SEARCH_QUERIES

API_KEY_FILE = Path(os.path.expanduser("~/.openclaw/secrets/google-cse.key"))
CX_FILE = Path(os.path.expanduser("~/.openclaw/secrets/google-cse.cx"))


def is_configured() -> bool:
    return API_KEY_FILE.exists() and CX_FILE.exists()


def _load_creds() -> tuple[str, str] | None:
    if not is_configured():
        return None
    key = API_KEY_FILE.read_text(encoding="utf-8").strip()
    cx = CX_FILE.read_text(encoding="utf-8").strip()
    if not key or not cx:
        return None
    return key, cx


def search_fb_posts(
    market_name: str,
    fb_handle: str,
    *,
    num: int = 5,
    query: str | None = None,
) -> list[dict]:
    """Search for FB posts via Google CSE. Returns normalized post dicts."""
    creds = _load_creds()
    if not creds:
        return []
    key, cx = creds
    queries = [query] if query else [q.format(handle=fb_handle) for q in SEARCH_QUERIES]
    all_results: list[dict] = []
    seen_ids: set[str] = set()

    for q in queries:
        if len(all_results) >= num:
            break
        params = {"key": key, "cx": cx, "q": q, "num": str(min(num, 10))}
        url = "https://www.googleapis.com/customsearch/v1?" + urllib.parse.urlencode(params)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "lobster-monitor"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            print(f"  [google-cse error] {market_name}: {type(e).__name__}: {e}", flush=True)
            continue

        for item in data.get("items", []):
            link = item.get("link", "")
            post_id = "gcs-" + hashlib.sha256(link.encode("utf-8")).hexdigest()[:16]
            if post_id in seen_ids:
                continue
            seen_ids.add(post_id)
            title = item.get("title", "")
            snippet = item.get("snippet", "")
            text = f"{title}. {snippet}"
            all_results.append(
                {
                    "market": market_name,
                    "post_id": post_id,
                    "timestamp": "",
                    "text": text,
                    "url": link,
                    "source": "google_cse",
                    "source_quality": 0.7,
                }
            )
            if len(all_results) >= num:
                break

    return all_results[:num]
