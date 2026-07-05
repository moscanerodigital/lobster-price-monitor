"""Google Custom Search JSON API client — fallback for FB-blocked markets.

Uses the Programmable Search Engine JSON API to run `site:facebook.com/<handle>`
queries that return FB post snippets indexed by Google. Each snippet often
contains the price text directly (e.g. "Live Lobster prices: Chicks $8.75 lb").

Free tier: 100 queries/day. Estimated use: 5 markets × 6 cron runs/day = 30.

Required env / secrets:
  - GOOGLE_CSE_API_KEY  — at ~/.openclaw/secrets/google-cse.key
  - GOOGLE_CSE_CX       — at ~/.openclaw/secrets/google-cse.cx

To obtain:
  1. Create a Programmable Search Engine at https://programmablesearchengine.google.com/
     - "Search the entire web" (not restricted to specific sites)
  2. Get the cx from the engine's setup page
  3. Create an API key at https://console.cloud.google.com/apis/credentials
     - Enable "Custom Search API" for the project first
"""
from __future__ import annotations
import json
import os
import urllib.parse
import urllib.request
from pathlib import Path

API_KEY_FILE = Path(os.path.expanduser("~/.openclaw/secrets/google-cse.key"))
CX_FILE = Path(os.path.expanduser("~/.openclaw/secrets/google-cse.cx"))


def is_configured() -> bool:
    """True if both key + cx are present on disk."""
    return API_KEY_FILE.exists() and CX_FILE.exists()


def _load_creds() -> tuple[str, str] | None:
    if not is_configured():
        return None
    key = API_KEY_FILE.read_text(encoding="utf-8").strip()
    cx = CX_FILE.read_text(encoding="utf-8").strip()
    if not key or not cx:
        return None
    return key, cx


def search_fb_posts(market_name: str, fb_handle: str, *, num: int = 5) -> list[dict]:
    """Search for the market's most recent FB posts via Google CSE.

    Returns list of normalized post dicts (same shape as the FB-scraper output):
      {market, post_id, timestamp, text, url, source}

    Returns [] on any failure (missing creds, network error, quota).
    """
    creds = _load_creds()
    if not creds:
        return []
    key, cx = creds
    # Query: site:facebook.com/<handle> lobster price
    # Use a recent-restricting hint to bias toward current prices
    query = f"site:facebook.com/{fb_handle} lobster price"
    params = {
        "key": key,
        "cx": cx,
        "q": query,
        "num": str(num),
        # Bias to recent (Google CSE doesn't support date range in free tier,
        # but `sort` may help)
    }
    url = "https://www.googleapis.com/customsearch/v1?" + urllib.parse.urlencode(params)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "lobster-monitor"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"  [google-cse error] {market_name}: {type(e).__name__}: {e}", flush=True)
        return []
    items = data.get("items", [])
    results: list[dict] = []
    for item in items:
        # Use Google's URL as a stable post_id; CSE doesn't expose the underlying FB post id
        # but the link is unique per result.
        url = item.get("link", "")
        # post_id = last 24 chars of the URL hash — stable for the same result
        import hashlib
        post_id = "gcs-" + hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
        title = item.get("title", "")
        snippet = item.get("snippet", "")
        # Combine title + snippet as the "text" of the post
        text = f"{title}. {snippet}"
        results.append({
            "market": market_name,
            "post_id": post_id,
            "timestamp": "",  # Google doesn't expose post timestamp in CSE
            "text": text,
            "url": url,
            "source": "google_cse",
        })
    return results
