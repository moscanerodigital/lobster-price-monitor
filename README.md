# Lobster Price Monitor

Tracks live lobster prices and daily-specials posts from 9 Maine coastal market sources on Erik's watchlist. Pages you on Telegram when any lobster tier or oyster grade drops below threshold.

**Markets covered**:

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
| Five Islands Lobster Co. | Georgetown | FB |

**Note:** 6 of 9 market sources post only to Facebook. Meta's anti-scrape policy blocks unauthenticated pulls on public pages. The 3 markets with structured web catalogs (Pine Tree, Harbor Fish lobster, Harbor Fish oysters) work today without authentication. To unlock the FB-only markets, export your Facebook session cookies and drop them at `~/.openclaw/secrets/facebook-cookies.json` (see [setup_fb_cookies.md](setup_fb_cookies.md)).

## Quick start

See **[DEPLOYMENT.md](DEPLOYMENT.md)** for Mac mini / Chromebox install, scrape, serve, health check, and scheduling.

**Production host deployment:** See **[NEXT_AGENT.md](NEXT_AGENT.md)** for the phased handoff runbook. One command: `make deploy-host` (phases 1–2; add `--promote` for live Telegram).

```bash
bash scripts/install.sh
bash scripts/dry_run.sh                    # scrape --no-alerts + board.html
make verify                                # unit tests + AAA gate (auto-seeds CI fixtures if needed)
make install-scheduler                     # host: dry-run scrape + serve + health schedulers
make verify-production-ci                  # Gate C smoke (B+ fixtures, skip scheduling)
make verify-deploy-ci                      # Deploy gate smoke (scheduler checks skipped)
make verify-ops-ci                         # Gate D smoke (learnings + ops verifier)
make deploy-host                           # host: phases 1–2 bootstrap + scheduler
make upgrade-host                          # host: in-place pull + deps + scheduler reload
make teardown-host                         # host: remove all schedulers
make bootstrap-host                        # host: phase 1 only
.venv/bin/python scripts/health_check.py
make serve                                 # http://127.0.0.1:8765/board.html (JSONL data not exposed)
.venv/bin/python scripts/board.py --html --open
```

**Telegram is off by default** — pass `--alerts` to `scrape_markets.py` only when approved.

The board server only serves `board.html`; requests for `prices.jsonl` and other data files return 403.

## Architecture

```
scripts/
├── scrape_markets.py    # Main entrypoint (AAA-gated pipeline)
├── parse_prices.py      # Price regex + tier/special extraction
├── parse_web.py         # WooCommerce HTML parser
├── quality_gate.py      # Source quality + confidence + plausibility gates
├── send_alert.py        # Telegram alerts (deduped, structured specials)
├── secrets.py           # FB cookies + Telegram chat ID loading
├── market_names.py      # Canonical short market display names
├── search_queries.py    # Shared FB search query templates
├── specials.py          # Query CLI for gated specials
├── markets.py           # Configured market/source roster
├── board.py             # Seafood chalkboard display (terminal + HTML)
├── board_render.py      # Board rendering engine
├── serve_board.py       # Hardened static board HTTP server
├── health_check.py      # Readiness report (--log for daily snapshots)
├── state.py             # JSONL read-or-bootstrap helpers
├── test_*.py            # Unit and gate tests
└── verify_*.py          # AAA / B+ / production / ops gate verifiers
```

CI runs `make verify-ci`, `make verify-next-ci`, `make verify-deploy-ci`, `make verify-production-ci`, and `make verify-ops-ci` on push via GitHub Actions (`.github/workflows/verify.yml`).

Per-run pipeline:
1. For each market, try FB public page (with optional cookies). Fallback chain: Google CSE → DuckDuckGo (specials-aware queries).
2. If market has a `web` URL, scrape the WooCommerce catalog and parse structured products.
3. Run `parse_prices.parse_post` (or use pre-parsed structured rows) to extract lobster tiers, oyster grades, and specials.
4. Pass all rows through `quality_gate.gate_rows()` — quarantine low-confidence/stale/out-of-band rows.
5. For gated rows, check against thresholds. Send Telegram if under threshold AND not deduped.
6. Specials alerts (AC4b): only posts with seafood keywords + `$`, with structured item list and confidence ≥70.
7. Web catalog specials: diff against last snapshot, alert on new items.
8. Persist everything to JSONL. Write run-stats row.

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

See [DEPLOYMENT.md](DEPLOYMENT.md) for launchd, systemd, and cron examples. Recommended cadence:
- **Weekdays:** 4×/day (07:00, 11:00, 15:00, 19:00 ET)
- **Weekends:** 2×/day (09:00, 17:00 ET)

## License

MIT — see `LICENSE`.

## Author

Built by Erik's OpenClaw concierge in July 2026. See `RALPH.md` for the full scaffolding history.
