# Lobster Price Monitor

Tracks live lobster prices and daily-specials posts from 8 Maine coastal markets within 15 mi of Gorham, ME. Pages you on Telegram when any lobster tier or oyster grade drops below threshold.

**Markets covered** (all within 15 mi of Gorham, ME):

| Market | Location | Source |
|---|---|---|
| Ancient Mariner Lobster Co. | Westbrook | FB |
| Two Tides Seafood | Scarborough | FB |
| Scarborough Fish & Lobster | Scarborough | FB |
| Pine Tree Seafood & Produce | Scarborough | pinetreeseafood.com (WooCommerce) |
| Harbor Fish Market (Lobster) | Portland + Scarborough | harborfish.com (WooCommerce) |
| Harbor Fish Market (Oysters) | Portland + Scarborough | harborfish.com (WooCommerce) |
| Free Range Fish & Lobster | Portland | FB |
| SoPo Seafood Market & Raw Bar | South Portland | FB |

**Note:** 5 of 8 markets post only to Facebook. Meta's anti-scrape policy blocks unauthenticated pulls on public pages. The 3 markets with structured web catalogs (Pine Tree, Harbor Fish lobster, Harbor Fish oysters) work today without authentication. To unlock the FB-only markets, export your Facebook session cookies and drop them at `~/.openclaw/secrets/facebook-cookies.json` (instructions in `RALPH.md` §Pitfalls).

## Quick start

```bash
# Install deps
python3 -m pip install facebook-scraper lxml_html_clean

# Run once
python3 scripts/scrape_markets.py

# Verify
bash scripts/verify_completion.sh
```

## Architecture

```
scripts/
├── scrape_markets.py    # Main entrypoint
├── parse_prices.py      # Price regex + tier extraction
├── parse_web.py         # WooCommerce HTML parser
├── send_alert.py        # Telegram alerts (deduped)
├── state.py             # JSONL read-or-bootstrap helpers
├── test_parse.py        # 11 unit tests for parse_prices
└── verify_completion.sh # 5-check AC verifier
```

Per-run pipeline:
1. For each market, try FB public page (via `facebook-scraper`). If empty + Google CSE creds, fall back to `site:facebook.com/<handle>` search.
2. If market has a `web` URL, scrape the WooCommerce catalog and parse structured products.
3. Run `parse_prices.parse_post` (or use pre-parsed structured rows) to extract lobster tiers, oyster grades, and specials.
4. For each parsed row, check against `LOBSTER_TIER_THRESHOLDS` / `OYSTER_TIER_THRESHOLDS`. Send Telegram if under threshold AND not deduped.
5. Persist everything to JSONL. Write a run-stats row.

## Thresholds (editable in `scripts/scrape_markets.py`)

```python
LOBSTER_TIER_THRESHOLDS = {
    "chicks": 7.50,        # $/lb
    "soft_shell": 8.00,
    "old_shell": 8.50,
    "hard_shell": 9.50,
    "select": 10.00,
    "1.125lb": 7.50, "1.25lb": 8.00, "1.5lb": 9.00, "1.75lb": 10.00,
    "2lb_plus": 11.00,
}

OYSTER_TIER_THRESHOLDS = {
    "xl": 28.00, "jumbo": 26.00, "select": 22.00, "standard": 18.00,
    "single_select": 32.00, "named_variety": 24.00,
    "small": 18.00, "medium": 20.00, "large": 24.00, "pint": 30.00,
    "oyster": 22.00,  # generic fallback
}
```

Per-lb oyster prices (common in wholesale) are converted to per-dozen equivalent by ×12 for threshold comparison.

## Alert format

```
🦞 *Lobster price drop* — Pine Tree Seafood & Produce
   hard_shell: $9.50/lb (threshold $9.50/lb)
   seen: 2026-07-04T15:30:00Z
   https://pinetreeseafood.com/shop
```

```
🦪 *Oyster price drop* — Harbor Fish Market (Oysters)
   xl: $32.00/doz (threshold $28.00/doz)
   seen: 2026-07-04T15:30:00Z
   https://harborfish.com/...
```

## Cron

Set up via `cronjob` MCP on the host. Recommended cadence:
- **Weekdays:** 4×/day (07:00, 11:00, 15:00, 19:00 ET)
- **Weekends:** 2×/day (09:00, 17:00 ET)

## License

MIT — see `LICENSE`.

## Author

Built by Erik's OpenClaw concierge in July 2026. See `RALPH.md` for the full scaffolding history.
