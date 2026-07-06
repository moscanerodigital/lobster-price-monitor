# SPRINT.md — Production Board Sprint (Composer 2.5 Multi-Agent)

**Created:** 2026-07-06 (wraps Fable 5 session findings)  
**Baseline commit:** `bd7771b` (`main`)  
**Prior session:** ~15 rapid commits (`0f73eee` → `bd7771b`) — caps, oysters, logos, layout, Five Islands manual import  
**Status at sprint start:** ~70–80% to production; board serves at `:8765`  
**Wave 3 complete (2026-07-06):** B-05 runtime guard, B-04 tests, C-03 visual QA, D-04 scrape (partial coverage), E-03 dev verify + serving-host runbook below.  
**Wave 4 complete (2026-07-06):** A-05 menu Gate B, A-06 oyster units, D-05 FB fetch (6/9 curl markets), E-04 deploy at `~/lobster-price-monitor` (MacBook Pro stand-in; Mac Mini/Chromebox use same runbook).

### Wave 4 completion metrics (dev scrape 2026-07-06T18:22Z)

| Metric | Result | D-04 bar | Notes |
|--------|--------|----------|-------|
| Lobster headlines | 8 | 8 | All markets with lobster data |
| Oysters (board) | 3 | ≥5 | 25 gated specials in prices.jsonl; board render shows 19 |
| Specials (board) | 19 | ≥25 | 4 markets on specials section |
| Gated rows | 54 | — | Gate B menu path uses raw confidence for FB menu posts |
| FB curl markets | 6/9 | ≥6/9 | Ancient Mariner, Pine Tree, Harbor (×2), Free Range, SoPo |

**Serving host (`~/lobster-price-monitor`):** `make install-scheduler`, full scrape, `make verify-production-ci` pass, `make status-host` pass, serve on `:8765`. D-04 display bar still partial — board filters drop 6 specials; oyster FB rows need parser follow-up.

### Wave 3 completion metrics (dev scrape 2026-07-06T18:10Z)

| Metric | Result | D-04 bar | Notes |
|--------|--------|----------|-------|
| Lobster headlines | 8 | 8 | All markets with lobster data |
| Oysters | 3 | ≥5 | Harbor Fish web only; FB oyster rows still quarantined |
| Specials (board) | 19 | ≥25 | 24 gated rows; 3 markets (Harbor Fish, Pine Tree, Ancient Mariner) |
| Gated rows | 53–56 | — | FB curl returned posts for 2/9 markets; others used history fallback |
| Board publish guard | active | — | Skips publish when passed rows &lt;40 or &lt;60% of pre-scrape |

**Remaining for full D-04 bar:** Refresh FB cookies; most markets returned zero `<article>` posts despite cookies file present. Re-run `bash scripts/dry_run.sh` after cookie refresh or on serving host with live session.

### E-03 serving-host checklist (run after `git pull`)

```bash
cd "$LOBSTER_ROOT"    # e.g. ~/lobster-price-monitor — NOT ~/Documents
git pull
bash scripts/preflight_secrets.sh
make import-five-islands
make upgrade-host
make verify-deploy
make status-host
curl -sf http://127.0.0.1:8765/board.html | head -c 500
```

**Dev laptop (2026-07-06):** `make verify-core`, `make verify-visual`, and `verify_deploy_gate.py --skip-scheduling` passed; `curl` board OK on `:8765`. Full `make verify-deploy` requires launchd serve agent running (serving host).

> **Note:** The audit/sprint-draft agent (`0dbf344c`) and label-bug agent (`ff9e8fb2`) were **aborted** before landing commits. This document merges their intended output with the **Fable 5 findings ledger** (see Appendix A).

---

## Sprint goal

Deliver a **production-grade Maine Coast Seafood Board** that Erik can pull on the serving host and trust daily:

| Criterion | Production bar |
|-----------|----------------|
| **Accuracy** | Every displayed price traceable to a gated `prices.jsonl` row; no untraceable or contradictory units |
| **Coverage** | All 9 markets represented where source data exists; blockers labeled honestly |
| **Freshness** | Web catalog rows ≤24h on weekdays; FB rows ≤48h or demoted when web is fresher |
| **Specials value** | Specific product names, sane prices, multi-market presence (not just Harbor Fish + Pine Tree) |
| **Oysters** | Variety + unit correct per row; multiple markets when data exists |
| **UI** | Desktop one-screen chalkboard feel; large logos; no nested scroll panes; mobile usable |
| **Ops** | Serving host: `git pull` + healthy scrape scheduler; board publish after scrape completes |

---

## User UI constraints (do not regress)

Established during Fable 5 — **mandatory** for all UI track work:

1. **Logos:** Large and prominent — desktop **80–96px** (`clamp(5rem, 6vw, 6rem)`), mobile **64px** minimum. Bare circular badges; **no wood frames** around logos.
2. **Layout:** **No nested column scroll** (`overflow-y: auto` on `.market-groups` is forbidden). One-screen “real board” on desktop; at most **one body scroll** on 1080p.
3. **Market grouping:** Items under market logo/text sign — not `"Market — Item"` prefixes on every row.
4. **Desktop width:** Frame up to **1050px** at 1024px+; two-row grid (lobster+oyster top, specials full width below) per `1f195cc`.
5. **Logos in git:** Base64 embedded in `data/board.html` so serving host needs only `git pull` (no separate static asset path).

---

## Workstreams

| Track | Owner scope | Primary files | Serialize with |
|-------|-------------|---------------|----------------|
| **A — Parser & gate** | `parse_prices.py`, `parse_web.py`, `quality_gate.py`, tests | No `chalk_board_html.py` | B after A-03 |
| **B — Board render** | `board_render.py`, `board.py`, render tests | No CSS | C after B-02 |
| **C — UI / CSS** | `chalk_board_html.py`, `market_logos.py`, visual QA | No parser logic | B |
| **D — Data & scrape** | `scrape_markets.py`, `markets.py`, `manual_import.py`, secrets | Regenerates `data/*` | A, B before final board |
| **E — Ops & deploy** | `DEPLOYMENT.md`, launchd, `serve_board.py`, CI, host scripts | No render/parser | Independent |

### Merge-conflict hotspots

- **`data/board.html`** — only one agent regenerates per integration pass (Track D or integration lead).
- **`scripts/chalk_board_html.py`** — Track C only; never parallel with B editing display helpers.
- **`scripts/board_render.py`** — Track B only; large file (~1500 lines).

### Parallel execution map

```
Wave 1 (parallel):  A-01, A-02, A-04, C-01, C-02, D-01, E-01, E-02
Wave 2 (parallel):  A-03, B-01, B-03, D-02, D-03
Wave 3 (serialize): B-02 → C-03 → D-04 (scrape + board regen) → E-03 (verify + push)
```

---

## Track A — Parser & quality gate

### A-01: Clause boundary hardening (S)

**Problem:** Newlines and bullets (`•`) were not clause boundaries — caused Ancient Mariner `$15.99` 2+lb bound to `hard_shell`, SoPo mashup rows. Regex clause logic is patch-on-patch.

**Files:** `scripts/parse_prices.py` (`_clause_of`, `_find_tier_left_of`)  
**Acceptance:** Regression test with Ancient Mariner multi-line menu; each size tier gets correct key; no section-header price binding.  
**Deps:** None

### A-02: FB menu confidence at scale (M)

**Problem:** Gate B floor 70 blocks legitimate FB menu specials at 45–68. `FB_MENU_SPECIALS_CONFIDENCE_BOOST = 15` added (`quality_gate.py:103`) but untested across all 9 markets.

**Files:** `scripts/quality_gate.py`, `scripts/test_quality_gate.py`  
**Acceptance:** Two Tides menu post: ≥8 specials pass gate; quarantine rate for `kind=special` drops measurably in fixture scrape.  
**Deps:** None

### A-03: Species misclassification guards (M)

**Problem:** Steamers/clams near lobster keywords → false `lobster_tier`; oysters `$X each` misclassified as scallops/swordfish specials; `$3` crab rows may be per-oz.

**Files:** `scripts/parse_prices.py`, `scripts/test_parse.py`  
**Acceptance:** Clams/steamers never emit `lobster_tier`; `$1.50 each` oyster path wins over special; Snow crab / Lob-crab rows have verified unit from FB snippet.  
**Deps:** A-01

### A-04: Web catalog key canonicalization (S)

**Problem:** Long non-canonical keys (>30 chars) took −20 penalty; salmon/tuna collapsed to generic keys (fixed partially via title-slug).

**Files:** `scripts/parse_web.py`, `scripts/test_parse_web.py`  
**Acceptance:** Pine Tree smoked products and Harbor Fish salmon/tuna lines get distinct stable keys with confidence ≥70.  
**Deps:** None

---

## Track B — Board render refactor

### B-01: Split board_render.py (L)

**Problem:** ~1500 lines accumulated caps, salvage, demotion, cull filters, label cleanup in one file — structural debt.

**Files:** Extract `board_labels.py`, `board_lobster.py`, `board_specials.py` from `board_render.py`; keep `build_board()` API stable.  
**Acceptance:** All existing tests pass; no behavior change; file line counts <400 each.  
**Deps:** None (Wave 2)

### B-02: Oyster & special label correctness (S) — **DONE** (Wave 1 `bb2aa1c`)

**Problem:** `chalk_board_html.py:38-39,95` hardcodes `"per dozen"` when label is `"Oysters"` even for `unit=ea` rows ($1.50, $1.65, $3). User-reported with screenshot.

**Files:** `scripts/chalk_board_html.py`, `scripts/board_render.py` (ensure `row_secondary` set for oysters)  
**Acceptance:** Free Range shows `$1.50 ea` with secondary `"each"` or variety name; Harbor Fish doz row shows `"per dozen"`; no row shows contradictory unit text.  
**Deps:** B-01 optional; can ship standalone first

### B-03: Cryptic special label filter (S) — **DONE** (Wave 1 `bb2aa1c`)

**Problem:** `"Lob/crab"` displays at $39/lb (Two Tides) — unreadable abbreviation. Expand from FB snippet or reject keys with `/` and length <8 without `catalog_title`.

**Files:** `scripts/board_render.py` (`_special_display_label`, `_is_clean_special_row`)  
**Acceptance:** No cryptic abbreviations on board; Lob/crab expands to readable name or is filtered; test covers slash-abbrev keys.  
**Deps:** A-03 for source truth

### B-04: Lobster headline accuracy (M) — **DONE** (Wave 3)

**Problem:** `_shell_from_key` maps `1.125lb`/`chicks` to `"hard"` without evidence; cull-snippet filter suppresses valid soft-shell (`board_render.py:759-801`).

**Files:** `scripts/board_render.py`  
**Acceptance:** Two Tides tier label matches FB post shell type; Ancient Mariner soft $13.99 visible when gated.  
**Deps:** A-01

### B-05: Publish-after-scrape gate (S) — **DONE** (Wave 3: static order + runtime completeness guard)

**Problem:** First Monday publish shipped 4 wrong prices from intermediate snapshot (Scarborough $12.50, salmon $14.99 untraceable).

**Files:** `scripts/scrape_markets.py` (`write_html_board` at ~728), `scripts/verify_deploy_gate.py`  
**Acceptance:** `write_html_board()` only after full pipeline; deploy gate fails if `board.html` `updated_at` predates latest `run-log.jsonl` ts.  
**Deps:** None

---

## Track C — UI / CSS consolidation

### C-01: CSS consolidation pass (M)

**Problem:** Six redesigns in one day — accreted `@media` blocks, conflicting logo sizes, duplicate market-group rules.

**Files:** `scripts/chalk_board_html.py`  
**Acceptance:** Single source of truth for breakpoints (480 / 768 / 1024); user UI constraints section satisfied; Playwright screenshots at 1440px and 480px attached or in `data/qa/`.  
**Deps:** None

### C-02: Fit viewport without nested scroll (M)

**Problem:** Doc height ~1540px on 1080p — user wants one-screen board; may need density tuning not logo shrink.

**Files:** `scripts/chalk_board_html.py`  
**Acceptance:** 1080p viewport: no `.market-groups` scroll; body height ≤1200px OR user accepts single page scroll; logos remain ≥80px desktop.  
**Deps:** C-01

### C-03: Integration visual QA (S) — **DONE** (Wave 3: `scripts/test_board_visual.py`, `make verify-visual`)

**Problem:** No automated visual regression.

**Files:** `scripts/test_board_visual.py` (new) or Playwright in CI  
**Acceptance:** Screenshot diff or structural asserts (section counts, no `Lob/crab`, no `per dozen`+`ea` mismatch).  
**Deps:** B-02, B-03, C-02

---

## Track D — Data coverage & scrape

### D-01: FB cookies unlock path (M)

**Problem:** 6/9 markets FB-only; cookies at `~/.openclaw/secrets/facebook-cookies.json` are the biggest unlock.

**Files:** `scripts/fb_curl_fetch.py`, `scripts/scrape_markets.py`, `DEPLOYMENT.md`  
**Acceptance:** With cookies present, ≥6 markets fetch FB posts; without, blockers documented per market in coverage.  
**Deps:** None

### D-02: History fallback when gate zeros out (S)

**Problem:** `recent_history_posts` only when `posts` empty (`scrape_markets.py:531`), not when all rows quarantine.

**Files:** `scripts/scrape_markets.py`, `scripts/state.py`  
**Acceptance:** Five Islands / SoPo retain last-good gated rows when fresh fetch quarantines everything.  
**Deps:** A-02

### D-03: Five Islands reference + manual import workflow (S)

**Problem:** Reference menu has no $/lb; board uses manual imports ($14.99/$15.99). Local-only in gitignored `prices.jsonl`.

**Files:** `scripts/manual_import.py`, `scripts/markets.py`, `DEPLOYMENT.md`  
**Acceptance:** Documented one-command import; `make import-five-islands` target; serving-host runbook step; prices verified against wharf reality.  
**Deps:** None

### D-04: Full scrape + board publish (S) — **PARTIAL** (Wave 4: 25 gated specials, 19 on board; oysters 3/5)

**Problem:** Serving host and git only get `board.html`; local state not portable.

**Files:** `data/board.html`, `data/prices.jsonl` (local)  
**Acceptance:** Post-scrape board: 8 lobster, ≥5 oyster, ≥25 specials, 9 live markets; commit `data/board.html` only after B-05 gate passes.  
**Deps:** A-*, B-*, Wave 3 integration

---

## Track E — Ops & production deploy

### E-01: Serving host path outside Documents (M)

**Problem:** launchd scrape fails exit 78 on dev laptop (`~/Documents` TCC). Production host must use `~/lobster-price-monitor` or `/opt/...`.

**Files:** `DEPLOYMENT.md`, `deploy/launchd/*.plist`  
**Acceptance:** `make install-scheduler` on clean path; `launchctl print` shows exit 0 after scheduled run.  
**Deps:** None

### E-02: CI board.html freshness check (S)

**Problem:** CI does not verify committed board matches parser output.

**Files:** `.github/workflows/verify.yml`, `scripts/verify_deploy_gate.py`  
**Acceptance:** CI fails if `board.html` stale vs fixtures or missing demo markers in production mode.  
**Deps:** B-05

### E-03: Production integration checklist (S) — **DONE** (dev verify); serving host: run checklist above after pull

**Run on serving host after sprint:**

```bash
cd "$LOBSTER_ROOT"
git pull
make upgrade-host          # or: scrape + board regen
make verify-deploy
make status-host
curl -sf http://127.0.0.1:8765/board.html | head -c 500
```

**Acceptance:** All verify gates pass; 9 live markets; no blocked footer entries without reason.

---

## Verification gates (per track)

| Track | Gate command |
|-------|----------------|
| A | `.venv/bin/python -m pytest scripts/test_parse.py scripts/test_parse_web.py scripts/test_quality_gate.py -q` |
| B | `.venv/bin/python -m pytest scripts/test_specials.py scripts/test_aaa_gate.py -q` |
| C | Manual: Playwright 1440×900 + 390×844; or `scripts/test_board_visual.py` |
| D | `bash scripts/dry_run.sh && .venv/bin/python scripts/health_check.py` |
| E | `make verify-core && make verify-deploy` |
| **Final** | `make verify-ci` + visual QA + `gpa` with fresh `data/board.html` |

---

## Top 10 problems (severity-ranked)

| # | Sev | Problem | Track |
|---|-----|---------|-------|
| 1 | **P0** | FB-only markets lack cookies → no live specials/oysters (6/9) | D-01 |
| 2 | **P0** | Oyster UI shows `"per dozen"` for `$X ea` rows (`chalk_board_html.py:38-39`) | B-02 |
| 3 | **P1** | Cryptic special labels (`Lob/crab`) on board | B-03, A-03 |
| 4 | **P1** | `board_render.py` structural debt — patch-on-patch | B-01 |
| 5 | **P1** | Publish race shipped wrong prices Monday AM | B-05 |
| 6 | **P1** | Gate B blocks valid FB menu specials (45–68 conf) | A-02 |
| 7 | **P2** | Gitignored local state — manual imports lost on serving host regen | D-03, D-04 |
| 8 | **P2** | CSS accreted across 6 redesigns — regression risk | C-01 |
| 9 | **P2** | History fallback too narrow (zero posts only) | D-02 |
| 10 | **P2** | 1080p still ~1540px body height | C-02 |

---

## Ticket summary

| Track | Tickets | S | M | L |
|-------|---------|---|---|---|
| A — Parser & gate | 4 | 2 | 2 | 0 |
| B — Board render | 5 | 3 | 1 | 1 |
| C — UI / CSS | 3 | 1 | 2 | 0 |
| D — Data & scrape | 4 | 3 | 1 | 0 |
| E — Ops & deploy | 3 | 2 | 1 | 0 |
| **Total** | **19** | **11** | **7** | **1** |

---

## Appendix A — Fable 5 session findings ledger

*Preserved verbatim from 2026-07-06 planning session. Do not delete.*

### Parser / gate pipeline

- Gate B confidence floor 70 blocks legitimate FB menu specials scoring 45–68 (Two Tides ~15 items, Free Range, SoPo). A +15 menu-post boost was added, but the floor/boost interaction is untested at scale.
- Long non-canonical web keys (>30 chars) took a −20 penalty; smoked-fish products needed canonicalization (partially fixed via title-slug keys).
- Price bands: shucked oysters $21.99 "1 Lb pkg" were quarantined as out-of-band $/lb; per-each oysters ($1.50–$3) fell below the default ea band. Bands were patched (`ea` $0.75–$5.00, pkg $12–$40) — needs regression coverage.
- Newlines and bullets (`•`) were not clause boundaries — caused Ancient Mariner section-header price binding ($15.99 2+lb bound to `hard_shell`) and SoPo mashup rows. Fixed but fragile; regex-based clause logic is patch-on-patch.
- Steamers/clams text near lobster keywords misparsed as `lobster_tier` (Two Tides $4.79, Ancient Mariner $7.99 clams).
- FB source-quality mis-tagging: curl-fetched posts sometimes tagged `facebook_search` (0.3 quality) → Gate A rejections of authentic posts.
- History fallback only triggers on zero posts fetched, not when posts exist but all rows quarantine (`scrape_markets.py` ~530).

### Board rendering

- `board_render.py` (~1500 lines) accumulated caps, salvage, demotion, cull filters, and label cleanup in one file today — structural debt, needs refactor track.
- Cull-snippet filter (`_LOBSTER_SNIPPET_REJECT`) suppressed valid Ancient Mariner soft-shell $13.99; heuristic loosened but still lexical (`board_render.py:759-801`).
- `_shell_from_key` maps bare size keys (`1.125lb`, `chicks`) to `"hard"` — Two Tides shows "hard" without evidence (`board_render.py:729`).
- Publish race: the first Monday board was committed from an intermediate snapshot; 4 wrong prices shipped (Scarborough $12.50 and salmon $14.99 untraceable in any data file). Board must be regenerated only after scrape fully completes.
- **OPEN at sprint start:** oyster rows show hardcoded `"per dozen"` secondary with `$1.50 ea` price (Free Range) — root cause `chalk_board_html.py:38-39,95`.
- **OPEN at sprint start:** cryptic special `"Lob/crab"` (Two Tides, $39/lb in current `build_board()`) — needs expansion or filter.
- Specials caps history: 6 total/2 per market → 36/10; oyster cap 4 → 16 (`board_render.py:938-941`). Round-robin behavior at higher counts unreviewed.

### UI / layout

- Six redesigns in one day: market wood signs (`11e4eba`), desktop widening 480→1050px (`26c3872`), logos added (`0c9f791`), enlarged (`fc205f3`), frames removed + Two Tides silhouette fixed (`2cff6b8`), balance pass (`809bf7b`) partially reverted by (`87f1987`), one-screen layout (`1f195cc`). CSS is accreted and needs consolidation.
- User constraints: logos large (80–96px desktop), no wood frames, no nested scroll panes, one-screen "real board" feel on desktop. Doc height still ~1540px on 1080p — one page scroll remains.
- Logo pipeline: FB Graph profile pics; placeholder detection rejects <1KB silhouettes; Two Tides re-fetched from page ID `99429853901`. Base64 embedded in `board.html`.

### Data coverage (product gaps)

- Specials: only Harbor Fish + Pine Tree have web catalogs; SoPo/Free Range/Two Tides FB rows are Jul 4–5 stale; Ancient Mariner, Scarborough, Five Islands have zero fish specials in source data.
- Oysters: 5 rows from 4 markets at sprint start; Pine Tree, Scarborough, Ancient Mariner, Five Islands have no oyster prices in any feed.
- Five Islands: reference menu has no $/lb prices; FB quarantined; board rows are manual imports ($14.99/$15.99 baseline from DEPLOYMENT.md) — prices need real-world verification.
- FB cookies at `~/.openclaw/secrets/facebook-cookies.json` are the single biggest data unlock (6 of 9 markets FB-only).

### Ops / deployment

- launchd scrape on dev laptop fails exit 78 (TCC blocks `~/Documents`); documented in `DEPLOYMENT.md` § Dev machine vs serving host. Dev machine scrapes manually, commits `data/board.html`, pushes; serving host pulls.
- `prices.jsonl` / `market-coverage.json` are gitignored — manual imports (Five Islands) and backfilled rows exist only in local state. Serving host must re-run imports or re-scrape.
- Web-specials snapshot diffing and dedup state also local-only; same portability concern.

### Session metrics (commit `bd7771b`)

| Metric | Value |
|--------|-------|
| Lobster markets on board | 8 |
| Oyster rows | 5 (4 markets) |
| Special rows | 28 (5 markets) |
| Markets live (footer) | 9 (after Five Islands `adc4833`) |
| Tests passing (last run) | 175+ |

### Session commit log (reference)

```
bd7771b Improve board specials quality, oyster parsing, and freshness filtering
1f195cc Remove nested column scroll on desktop chalk board
adc4833 Bring Five Islands live on the board via manual lobster prices
87f1987 Restore large prominent market logos on chalkboard
809bf7b Balance desktop chalkboard columns with compact layout and scroll
2cff6b8 Remove wood frames from market logos; fix Two Tides placeholder
fc205f3 Enlarge market logos on chalkboard signs for readability
0c9f791 Add market logos to chalkboard signs with logo-only display
3ad8029 Improve specials board quality with catalog variety keys and FB salvage
26c3872 Widen chalk board layout for desktop viewports
11e4eba Market chalkboard headings UI
ab9af9b Fix SoPo special label filtering
4dc38af Fix Ancient Mariner lobster price parsing
0f73eee Publish Monday board and document dev-vs-serving host handoff
```

---

## Appendix B — File:line reference index

| Topic | Location |
|-------|----------|
| Gate B threshold | `scripts/quality_gate.py:34` |
| FB menu boost | `scripts/quality_gate.py:103,269` |
| Special row cleanliness | `scripts/board_render.py:268` |
| Special caps | `scripts/board_render.py:940-941` |
| Oyster cap | `scripts/board_render.py:938` |
| Cull snippet reject | `scripts/board_render.py:759-801` |
| Shell from key | `scripts/board_render.py:729` |
| Oyster "per dozen" hardcode | `scripts/chalk_board_html.py:38-39,95` |
| History fallback | `scripts/scrape_markets.py:531` |
| Board write after scrape | `scripts/scrape_markets.py:728-730` |
| Market config | `scripts/markets.py` |
| Dev vs serving host | `DEPLOYMENT.md` § Dev machine vs serving host |
| CI verify | `.github/workflows/verify.yml` |
| Logo assets | `assets/logos/*.webp`, `scripts/market_logos.py` |

---

## Composer 2.5 multi-agent execution notes

1. **Assign one integration lead** for Wave 3 — sole owner of `git pull`, board regen, commit, `gpa`.
2. **Branch strategy:** feature branches per track (`sprint/a-parser`, `sprint/b-render`, …) merge to `main` at Wave 3.
3. **Do not** run parallel agents on `chalk_board_html.py` and `board_render.py`.
4. **Regenerate** `data/board.html` once after all code merges; never commit board from partial scrape.
5. **Preserve Appendix A** when editing this file — append new findings, do not replace history.
