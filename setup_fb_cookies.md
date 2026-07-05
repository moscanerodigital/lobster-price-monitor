# Facebook cookies for lobster-price-monitor

The scraper reads Facebook session cookies from a **local secrets file** (never committed to git). With valid cookies, `fb_curl_fetch` pulls posts directly from each market's public page — faster and more reliable than DuckDuckGo search fallback.

## Cookie file location

```
~/.openclaw/secrets/facebook-cookies.json
```

## Export from Chrome (recommended)

1. Log in to [facebook.com](https://www.facebook.com) in Chrome.
2. Install a cookie export extension (e.g. **EditThisCookie**, **Cookie-Editor**, or **Get cookies.txt LOCALLY**).
3. While on `facebook.com`, export cookies for domain `.facebook.com`.
4. Save as `facebook-cookies.json` in the path above.

## Supported JSON formats

**Array of cookie objects** (Chrome extension export):

```json
[
  {"name": "c_user", "value": "YOUR_USER_ID", "domain": ".facebook.com"},
  {"name": "xs", "value": "YOUR_XS_TOKEN", "domain": ".facebook.com"}
]
```

**Wrapped dict:**

```json
{
  "cookies": {
    "c_user": "YOUR_USER_ID",
    "xs": "YOUR_XS_TOKEN"
  }
}
```

**Flat dict:**

```json
{
  "c_user": "YOUR_USER_ID",
  "xs": "YOUR_XS_TOKEN"
}
```

The scraper requires at least `c_user` and `xs`.

## Fallback: read from Chrome directly

If no file exists, the scraper tries `browser_cookie3.chrome(domain_name=".facebook.com")` on the Mac mini host. This only works when Chrome has an active FB session on the same machine.

## Verify

```bash
.venv/bin/python scripts/scrape_markets.py --no-alerts
```

Look for `[fb curl] <market>: N posts` in output. Markets should complete in seconds per market (no 12-minute DDG crawl).

## Security

- **Do not** commit `facebook-cookies.json` or paste cookie values into chat, logs, or RALPH.md.
- Rotate cookies if they leak; treat `xs` like a password.
- File permissions: `chmod 600 ~/.openclaw/secrets/facebook-cookies.json`
