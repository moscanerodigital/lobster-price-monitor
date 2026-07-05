# RALPH.md — Maine Coastal Lobster & Specials Monitor

**Status:** ✅ GATE C PASSED (2026-07-05)
**Tier:** MALPH (3 runs × 30 min)
**Goal:** Track live lobster prices (per-lb, size-tiered) and full daily-specials posts from Erik's Maine coastal market watchlist. Page Erik on Telegram when any lobster tier drops below threshold OR a new specials post is detected.

## Pre-known findings (do not re-investigate)

**Source signal: Facebook public pages.** Several markets post weekly price updates + daily specials to public Facebook pages. Some include structured HTML on a website (Pine Tree and Harbor Fish).

**Markets + handles (verified by web search 2026-07-04):**

| # | Market | Location | FB handle | Notes |
|---|---|---|---|---|
| 1 | Ancient Mariner Lobster Co. | Westbrook | `amlobsterco` | Posts size-tiered live lobster prices weekly. Sample: chicks $8.75/lb, old shell $10.75, hard $11.95, 2lb+ $12.75. |
| 2 | Two Tides Seafood | Scarborough (397 Gorham Rd) | `100054888565201` | Posts "current menu prices" with size tiers. Sample: 1⅛ lb $7.99/lb, 1¼ lb $9.99, 1½ lb $10.89, 1¾ lb $. |
| 3 | Scarborough Fish & Lobster | Scarborough (697 US-1) | `CheapMaineLobster` | Posts lobster + seafood specials. |
| 4 | Pine Tree Seafood & Produce | Scarborough | `PineTreeSeafood` | Posts lobster rolls ($24.99), hard shell live ($22.50/lb 1.25 lb), meat ($69.99/lb). |
| 5 | Harbor Fish Market | Portland + Scarborough | `harborfishmarket` (FB) + harborfish.com (structured) | Both Facebook specials posts AND structured product pages. |
| 6 | Free Range Fish & Lobster | Portland | `freerangefishandlobster` | Added per Erik 2026-07-04. |
| 7 | SoPo Seafood Market & Raw Bar | South Portland (171 Ocean St) | `soposeafood` | Added per Erik 2026-07-04. |
| 8 | Five Islands Lobster Co. | Georgetown | `fiveislandslobsterco` | Added per Erik 2026-07-04. Official menu page exists, but price capture is FB-first until a page parser is added. |
| — | Pine Tree Seafood (web) | Scarborough | pinetreeseafood.com/shop | 59-product WooCommerce catalog. Scraped in parallel with FB. |
| — | Harbor Fish Market (web) | Portland | harborfish.com/product-category/all/lobster/live-lobster | Structured product page. Scraped in parallel with FB. |

**Facebook scraping caveat:** `facebook-scraper` library (PyPI: `facebook-scraper`, v0.2.59) works for public pages but requires `pages >= 2` (verified Jun 2026: pages=1 returns 0 results on Ancient Mariner, warning printed). Use `pages=3` for safety. Library is installed in `/Users/openclaw/.hermes/hermes-agent/venv` via `pip install facebook-scraper lxml_html_clean`. Smoke test pulled 0 posts from amlobsterco at `pages=1` — must be retested at `pages=3`.

**Alert delivery:** Telegram via existing `@MoscaGemBot` token at `~/.openclaw/secrets/telegram/herb.token`. Erik's home channel ID `6700324874`. Memory: "Mac Mini uses MoscaGemBot" — this is the Mac mini, so use MoscaGemBot, NOT CronBot.

**Run location:** `/Users/openclaw/hermes-data/projects/lobster-price-monitor/` (internal disk, not SSD wedge trap).

## Acceptance Criteria (MALPH, ≤5)

1. **AC1 — Multi-source scrape works.** Pull from each configured source: FB public pages (where accessible), WooCommerce web catalogs (Pine Tree + Harbor Fish live lobster + Harbor Fish oysters). Persist to `data/history.jsonl` with `market`, `post_id`, `timestamp`, `text`, `url`, `source`. Verify on disk after each run: row count grows, no two rows share the same `post_id` for the same market. **Target: ≥3 sources succeed (out of 9) per run — FB is best-effort due to Meta's no-scrape policy.**
2. **AC2 — Price parsing.** From each new post, extract lobster tiers (`<size> $<X>/lb`) and specials (`<item> $<X>[/lb]`). Persist parsed rows to `data/prices.jsonl` with `market`, `observed_at`, `tier` or `item`, `price`, `unit`. Match the existing FB-post style (e.g. "chicks 1 1/4 lb $8.75/lb" → `{tier: "chicks 1.25lb", price: 8.75, unit: "lb"}`).
3. **AC3 — Threshold alert — lobster.** When ANY lobster tier price drops below `LOBSTER_TIER_THRESHOLDS` (default: chicks $7.50, hard $9.50, 2lb+ $11.00), send a Telegram message to Erik's home channel with: market, tier, price, post URL, observed_at. If the same (market, tier, price) is seen twice in a row, suppress the second alert (dedupe). **Live lobster only** — cooked/picked meat, lobster bisque, lobster mac/ravioli are excluded.
4. **AC4 — Threshold alert — oysters.** When ANY oyster grade price drops below `OYSTER_TIER_THRESHOLDS` (per-dozen thresholds; per-lb price converted to per-dozen equivalent by ×12), send a Telegram message: market, grade, price, unit, post URL, observed_at. Dedupe by (market, grade, price, unit).
5. **AC4b — Specials post alert.** When a NEW FB post is detected that mentions ANY of `{halibut, scallops, clams, shrimp, haddock, salmon, chowder, roll}` and contains a `$` price, send a Telegram alert with the post text snippet (first 280 chars) and URL. Dedupe by `post_id`.
5. **AC5 — Run health.** Each run writes a `data/run-log.jsonl` entry: `{ts, markets_attempted, markets_succeeded, posts_pulled, prices_parsed, lobster_alerts, oyster_alerts, special_alerts, errors}`. Errors are non-fatal — a single market failing does not abort the run. Verify `markets_succeeded >= 3` for ≥2 consecutive runs before marking complete. FB-blocked markets (6/9) don't count as failures — only truly fatal errors (network down, missing token) do.

## Pitfalls

- **FB scrape at `pages=1` returns 0 posts** (smoke test confirmed). Use `pages=3`.
- **FB will rate-limit** with no cookies. The library handles this with backoff; if `MaxRetryError` fires, the run logs the failure and proceeds to next market. Do NOT abort the whole run on a single FB failure.
- **Telegram token in secrets file** — read via `open(os.path.expanduser("~/.openclaw/secrets/telegram/herb.token")).read().strip()`, NOT hardcoded. DO NOT echo the token in logs.
- **Lobster price parsing regex** must handle: `$8.75/lb`, `$8.75 lb`, `$8.75 per pound`, `$8.99lb`, `8.75/lb`. Use a single canonical regex: `\$\s*(\d+(?:\.\d+)?)\s*(?:/lb|per pound|per lb|lb|/ pound)` (case-insensitive).
- **Tier extraction**: words like "chicks", "chix", "soft shell", "old shell", "hard shell", "select", "2 lb and up" must all map to a canonical tier. Use a simple keyword map.
- **No-fake-data guard:** the verify-completion script must check that the data rows have real timestamps (within last 7 days) and real price values (not all the same number). Synthetic test data is a fail.
- **Cron tool redaction:** when writing the Telegram-token-reading code, do NOT inline the literal token in any prompt or log line. Read the file at runtime only.
- **Facebook blocking:** `facebook-scraper` library returns 0 posts on unauthenticated requests (verified Jul 4 2026 with `amlobsterco`, `100054888565201`, `CheapMaineLobster`, `PineTreeSeafood`, `harborfishmarket`, `freerangefishandlobster`, `soposeafood` — all 0; Five Islands expected same behavior until cookies are supplied). Meta has aggressive no-scrape on public pages. Two paths forward: (a) provide cookies (Erik would need to log in to FB and export cookies), (b) lean on the web-catalog sources that DO work (Pine Tree + Harbor Fish). The current scaffold does (b) and treats (a) as optional enhancement. Don't paper over (b) by trying random proxies — that creates fragility.
- **Patch-tool Bearer-header pitfall:** N/A here (no Bearer auth). But the same redaction layer collapses `$<token>` patterns — write the file with `open(...).read()` calls, not f-strings with the value.

## Schedule

- **Cron:** 4×/day on weekdays, 2×/day on weekends. Local ET.
  - Weekdays: 07:00, 11:00, 15:00, 19:00 ET
  - Weekends: 09:00, 17:00 ET
- **Cadence rationale:** Most markets post specials between 7-10am and during weekend mornings. 4× weekday catches both pre-open and after-lunch updates. Weekend markets are 9-6 only (per Nextdoor listing for Ancient Mariner).

## State layout

```
~/hermes-data/projects/lobster-price-monitor/
├── RALPH.md                # this file
├── README.md               # how to operate + thresholds
├── scripts/
│   ├── scrape_markets.py   # main scrape + parse + alert entrypoint
│   ├── parse_prices.py     # regex extraction (pure function, easily testable)
│   ├── send_alert.py       # Telegram send (dedupe-aware)
│   ├── state.py            # post_id / alert dedupe (read or bootstrap file)
│   └── verify_completion.sh
├── data/
│   ├── history.jsonl       # every FB post pulled, ever
│   ├── prices.jsonl        # parsed lobster tier + special rows
│   ├── alerts_sent.jsonl   # dedupe log (post_id + alert_kind)
│   └── run-log.jsonl       # one row per cron run
└── logs/
    └── scrape.log          # stderr from scrape_markets.py
```

## Gate status (2026-07-05)

| Gate | Status | Command |
|---|---|---|
| **AAA** | PASS | `.venv/bin/python scripts/verify_aaa_gate.py` |
| **B+** | PASS | `.venv/bin/python scripts/verify_next_gate.py` |
| **C (Production)** | PASS | `.venv/bin/python scripts/verify_production_gate.py` |
| **D (Ops)** | Planned | Live alerts on scheduler, host scheduling verify, RALPH learnings auto-capture |

**CI:** `make verify-ci` (AAA) · `make verify-next-ci` (Gate B+ with full 7-market fixtures)

**Gate B+ criteria:** AAA passes · all tests pass · every market with gated lobster data on the board (≥7 when Five Islands blocked) · footer coverage matches board · scrape &lt;24h · health smoke test · mobile board HTML.

**Gate C (Production) criteria:** Gate B+ passes · MALPH verify passes · local launchd/systemd scheduler registered & running · scrape duration < 300s · specials section parsed & rendered · Five Islands blocker safely isolated or manual price imported.

**Gate D (Ops) criteria (planned):** Gate C passes on host · `--alerts` enabled on scheduler · `verify_production_gate.py --skip-scheduling` passes in CI · RALPH Learnings auto-populated from run-log.

**Current reality (2026-07-05 scrape):** 8/9 markets live in scrape health; **7/8 lobster markets** on the public board. **Five Islands** partial — menu has no $/lb online; spam $5/lb quarantined; board shows nothing (correct).

### Per-market lobster board (latest scrape)

| Market | Board headline | Confidence | Source |
|---|---|---:|---|
| Two Tides | 1⅛ lb hard $7.99/lb | 90 | FB |
| SoPo Seafood | hard $8.95/lb | 80 | FB search |
| Free Range | chix soft $9.99/lb | 72 | FB search |
| Scarborough F&L | soft $10.99 · hard $9.99 | 72 | FB search |
| Ancient Mariner | soft $10.49 · hard $15.99 | 90 | FB |
| Pine Tree | soft $13.50 · hard $14.50 | 70 | Web catalog |
| Harbor Fish | soft $14.30 · hard $15.30 | 70 | Web + FB |
| Five Islands | — (partial) | — | No gated $/lb; see `setup_fb_cookies.md` |

**Ops:** `make verify-next` · `make verify-next-ci` · `make health` · mobile QA `data/qa/board-390px.png` · cookies doc `setup_fb_cookies.md`


## Learnings

<!-- auto-updated from run-log -->

- **Latest run** (2026-07-05T14:55:49.555711+00:00): 8/9 markets, 87.5s, avg conf 81.8; alerts: 0 lobster, 0 oyster, 0 specials
- **Five Islands Lobster Co.** (partial): Menu reference only — no live scrape

## Usage / Budget Log

(empty — populated by step 5 of "When done")
