# Facebook cookies setup (one-time)

Six Maine seafood markets post live lobster prices only on Facebook. Meta blocks unauthenticated scraping; the monitor reads your logged-in session via a cookie file.

## Export cookies once

1. In Chrome (or Brave), log in to [facebook.com](https://www.facebook.com) as yourself.
2. Visit a public market page to confirm you can see posts, e.g. [Ancient Mariner](https://www.facebook.com/amlobsterco).
3. Install a cookie export extension (e.g. **Get cookies.txt LOCALLY** or **EditThisCookie**).
4. Export cookies for domain `.facebook.com` as **JSON** (array of `{name, value, domain, ...}` objects).
5. Save the file to:

   ```
   ~/.openclaw/secrets/facebook-cookies.json
   ```

6. Verify required session keys are present (names only, not values):

   ```bash
   python3 -c "
   import json, os
   p = os.path.expanduser('~/.openclaw/secrets/facebook-cookies.json')
   names = {c['name'] for c in json.load(open(p))}
   print('c_user:', 'c_user' in names, 'xs:', 'xs' in names)
   "
   ```

   Both must be `True`.

## Alternative: use Chrome directly

If you skip the file, the scraper tries `browser_cookie3` to read cookies from your local Chrome profile. That only works when the scrape runs on the same machine where you are logged in to Facebook.

## Test

```bash
cd lobster-price-monitor
.venv/bin/python -c "
import sys; sys.path.insert(0,'scripts')
from fb_curl_fetch import fetch_fb_posts
posts = fetch_fb_posts('Ancient Mariner Lobster Co.', 'amlobsterco', max_posts=2)
print(len(posts), 'posts'); print(posts[0]['text'][:200] if posts else 'no posts')
"
```

## Security

- **Never commit** `facebook-cookies.json` or paste cookie values into chat.
- Cookies expire; re-export if markets flip back to "blocked" after weeks of working.
- File permissions: `chmod 600 ~/.openclaw/secrets/facebook-cookies.json`

## Run scrape

```bash
.venv/bin/python scripts/scrape_markets.py --no-alerts
```
