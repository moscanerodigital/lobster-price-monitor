"""DuckDuckGo HTML search fallback for FB-blocked markets."""
from __future__ import annotations
import hashlib
import re
import urllib.parse
import urllib.request

DDG_HTML_URL = "https://html.duckduckgo.com/html/"

SEARCH_QUERIES = [
    "site:facebook.com/{handle} lobster price",
    "site:facebook.com/{handle} specials halibut scallops",
    "site:facebook.com/{handle} daily special",
]


def _post_form(query: str) -> bytes:
    return urllib.parse.urlencode({"q": query}).encode("utf-8")


def _parse_ddg_html(html: str, market_name: str, *, num: int) -> list[dict]:
    if "captcha" in html.lower() or "anomaly" in html.lower():
        return []

    title_re = re.compile(
        r'<a[^>]*class="[^"]*\bresult__a\b[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
        re.DOTALL | re.IGNORECASE,
    )
    snippet_re = re.compile(
        r'<a[^>]*class="[^"]*\bresult__snippet\b[^"]*"[^>]*>(.*?)</a>',
        re.DOTALL | re.IGNORECASE,
    )
    results: list[dict] = []
    seen_urls: set[str] = set()
    for tm in title_re.finditer(html):
        url = tm.group(1)
        title_html = tm.group(2)
        if not url.startswith("http") or url in seen_urls:
            continue
        seen_urls.add(url)
        title = re.sub(r"<[^>]+>", "", title_html).strip()
        snippet = ""
        sn = snippet_re.search(html, tm.end())
        if sn:
            snippet = re.sub(r"<[^>]+>", "", sn.group(1)).strip()
        text = f"{title}. {snippet}" if snippet else title
        post_id = "ddg-" + hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
        results.append({
            "market": market_name,
            "post_id": post_id,
            "timestamp": "",
            "text": text,
            "url": url,
            "source": "duckduckgo",
            "source_quality": 0.5,
        })
        if len(results) >= num:
            break
    return results


def search_fb_posts(
    market_name: str,
    fb_handle: str,
    *,
    num: int = 5,
    query: str | None = None,
) -> list[dict]:
    """Search for FB posts via DDG HTML. Returns normalized post dicts."""
    queries = [query] if query else [q.format(handle=fb_handle) for q in SEARCH_QUERIES]
    all_results: list[dict] = []
    seen_ids: set[str] = set()

    for q in queries:
        if len(all_results) >= num:
            break
        try:
            req = urllib.request.Request(
                DDG_HTML_URL,
                data=_post_form(q),
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
            continue

        if "captcha" in html.lower() or "anomaly" in html.lower():
            print(f"  [ddg captcha] {market_name}: hit bot wall, skipping query", flush=True)
            continue

        for row in _parse_ddg_html(html, market_name, num=num):
            if row["post_id"] not in seen_ids:
                seen_ids.add(row["post_id"])
                all_results.append(row)
                if len(all_results) >= num:
                    break

    return all_results[:num]
