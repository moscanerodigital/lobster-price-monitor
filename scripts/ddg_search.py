"""DuckDuckGo HTML search fallback for FB-blocked markets.

DDG's HTML endpoint (https://html.duckduckgo.com/html/) is unauthenticated
and returns search results as server-rendered HTML. We use `site:facebook.com`
queries to find indexed FB post snippets containing price text.

Quality is lower than Google CSE (no JSON API, no `num > ~30`, no quota
controls) but the path is zero-setup and works on any host with outbound
HTTPS. DDG occasionally returns 202/captcha pages — handle gracefully.
"""
from __future__ import annotations
import json
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path


DDG_HTML_URL = "https://html.duckduckgo.com/html/"


def _post_form(query: str) -> bytes:
    return urllib.parse.urlencode({"q": query}).encode("utf-8")


def search_fb_posts(market_name: str, fb_handle: str, *, num: int = 5) -> list[dict]:
    """Search for the market's most recent FB posts via DDG HTML.

    Returns list of normalized post dicts (same shape as the FB-scraper output):
      {market, post_id, timestamp, text, url, source}

    Returns [] on any failure (network, captcha, parse).
    """
    query = f"site:facebook.com/{fb_handle} lobster price"
    try:
        req = urllib.request.Request(
            DDG_HTML_URL,
            data=_post_form(query),
            headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9",
                "Accept-Language": "en-US,en;q=0.5",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"  [ddg error] {market_name}: {type(e).__name__}: {e}", flush=True)
        return []

    # Captcha check — DDG sometimes returns a 202/JS challenge
    if "captcha" in html.lower() or "anomaly" in html.lower():
        print(f"  [ddg captcha] {market_name}: hit bot wall, skipping", flush=True)
        return []

    # Parse results. DDG HTML uses <a class="result__a" href="...">title</a>
    # and <a class="result__snippet">snippet</a>. Pattern is stable enough.
    # We grab pairs of (href, title) + snippets.
    import hashlib
    results: list[dict] = []
    # Match each result block
    # DDG wraps each result in <div class="result ...">...</div>
    block_re = re.compile(
        r'<div[^>]*class="[^"]*\bresult\b[^"]*"[^>]*>(.*?)</div>\s*</div>\s*</div>',
        re.DOTALL | re.IGNORECASE,
    )
    # If that pattern is too strict, fall back to a simpler per-link approach
    title_re = re.compile(
        r'<a[^>]*class="[^"]*\bresult__a\b[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
        re.DOTALL | re.IGNORECASE,
    )
    snippet_re = re.compile(
        r'<a[^>]*class="[^"]*\bresult__snippet\b[^"]*"[^>]*>(.*?)</a>',
        re.DOTALL | re.IGNORECASE,
    )
    seen_urls: set[str] = set()
    for tm in title_re.finditer(html):
        url = tm.group(1)
        title_html = tm.group(2)
        if not url.startswith("http") or url in seen_urls:
            continue
        seen_urls.add(url)
        title = re.sub(r"<[^>]+>", "", title_html).strip()
        # Find the next snippet after this title
        snippet = ""
        sn = snippet_re.search(html, tm.end())
        if sn:
            snippet = re.sub(r"<[^>]+>", "", sn.group(1)).strip()
        text = f"{title}. {snippet}" if snippet else title
        # post_id: stable hash of the URL
        post_id = "ddg-" + hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
        results.append({
            "market": market_name,
            "post_id": post_id,
            "timestamp": "",
            "text": text,
            "url": url,
            "source": "duckduckgo",
        })
        if len(results) >= num:
            break
    return results
