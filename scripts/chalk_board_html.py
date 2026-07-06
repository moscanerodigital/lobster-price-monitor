"""Clean, scannable chalkboard HTML — mobile-first price list."""

from __future__ import annotations

import html
import json

from board_render import _SECTION_META, _format_observed
from market_logos import logo_data_uri


def _group_items_by_market(items: list[dict]) -> list[tuple[str, list[dict]]]:
    """Preserve item order; cluster consecutive rows under each market."""
    groups: list[tuple[str, list[dict]]] = []
    index_by_market: dict[str, int] = {}
    for item in items:
        market_key = item.get("market") or item.get("market_short") or ""
        if market_key in index_by_market:
            groups[index_by_market[market_key]][1].append(item)
        else:
            index_by_market[market_key] = len(groups)
            groups.append((market_key, [item]))
    return groups


def _oyster_row_label(item: dict) -> str:
    """Grouped oyster row title — variety name or unit-aware secondary."""
    secondary = str(item.get("row_secondary") or "").strip()
    if secondary:
        return secondary
    label = str(item.get("label") or "")
    unit = str(item.get("unit") or item.get("unit_label", "")).replace("/", "").lower()
    if unit == "ea":
        return label if label.lower() != "oysters" else "each"
    if unit in {"doz", "dozen"}:
        return label if label.lower() != "oysters" else "per dozen"
    return label


def _item_label_without_market(item: dict, *, section_key: str) -> str:
    """Row title when a market sign heading is shown above the group."""
    if section_key == "special":
        row_primary = str(item.get("row_primary") or "")
        market_short = str(item.get("market_short") or "")
        sep = " — "
        if sep in row_primary and row_primary.startswith(market_short + sep):
            return row_primary[len(market_short) + len(sep) :]
        return str(item.get("label") or row_primary)
    if section_key == "lobster" and item.get("is_consolidated"):
        return str(item.get("row_secondary") or item.get("label") or "Lobster")
    if section_key == "oyster":
        return _oyster_row_label(item)
    return str(item.get("label") or "")


def _html_market_sign(market_short: str, *, section_key: str, tilt: float) -> str:
    name = html.escape(market_short)
    logo_uri = logo_data_uri(market_short)
    if logo_uri:
        inner = (
            f'<img class="market-sign-logo" src="{logo_uri}" alt="{name}" '
            f'width="96" height="96" decoding="async">'
        )
        sign_cls = f"market-sign market-sign--logo section-{section_key}"
    else:
        inner = f'<span class="market-sign-label">{name}</span>'
        sign_cls = f"market-sign market-sign--text section-{section_key}"
    return f'<div class="{sign_cls}">{inner}</div>'


def _html_price_row(item: dict, *, section_key: str, grouped_by_market: bool = False) -> str:
    market = html.escape(item.get("market_short", ""))
    label = html.escape(item.get("label", ""))
    raw_subtext = item.get("subtext", "")
    amount = html.escape(str(item.get("price_amount", item.get("price_str", "—"))))
    unit = html.escape(str(item.get("unit_label", "")))
    unavailable = item.get("is_unavailable")
    wide_price = amount.startswith("from ") or ("–" in amount and len(amount) > 10)

    if grouped_by_market:
        left_primary = html.escape(_item_label_without_market(item, section_key=section_key))
        if section_key == "lobster" and item.get("is_consolidated"):
            left_secondary = ""
            subtext = ""
        elif section_key == "special":
            left_secondary = ""
            subtext = html.escape(raw_subtext)
        else:
            left_secondary = ""
            subtext = html.escape(raw_subtext)
    elif section_key == "lobster":
        if item.get("is_consolidated"):
            left_primary = html.escape(item.get("row_primary", item.get("market_short", "")))
            left_secondary = html.escape(item.get("row_secondary") or raw_subtext or "")
            subtext = ""
        else:
            left_primary = market
            left_secondary = label
            subtext = html.escape(raw_subtext)
    elif section_key == "special":
        left_primary = html.escape(
            item.get("row_primary") or f"{item.get('market_short', '')} — {item.get('label', '')}"
        )
        left_secondary = ""
        subtext = html.escape(raw_subtext)
    else:
        left_primary = market
        left_secondary = _oyster_row_label(item) if section_key == "oyster" else label
        subtext = html.escape(raw_subtext)

    sub_html = f'<span class="row-subtext">{subtext}</span>' if subtext else ""
    secondary_html = (
        f'<span class="row-secondary">{left_secondary}</span>' if left_secondary else ""
    )
    price_cls = "row-price is-out" if unavailable else "row-price"
    row_cls = f"price-row section-{section_key}"
    if item.get("is_consolidated"):
        row_cls += " is-consolidated"
    amount_cls = "price-amount is-wide" if wide_price else "price-amount"

    return (
        f'<li class="{row_cls}">'
        f'<div class="row-left">'
        f'<span class="row-primary">{left_primary}{sub_html}</span>'
        f"{secondary_html}"
        f"</div>"
        f'<div class="{price_cls}">'
        f'<span class="{amount_cls}">{amount}</span>'
        f'<span class="price-unit">{unit}</span>'
        f"</div>"
        f"</li>"
    )


def _html_blocked_details(coverage: list[dict]) -> str:
    blocked = [c for c in coverage if c.get("status") in ("blocked", "partial")]
    if not blocked:
        return ""

    rows = []
    for entry in blocked:
        name = html.escape(entry.get("short", entry.get("name", "")))
        reason = html.escape(entry.get("reason") or entry.get("blocker") or "unavailable")
        status = entry.get("status", "blocked")
        tag = "partial" if status == "partial" else "blocked"
        rows.append(
            f'<li class="blocked-item {tag}">'
            f'<span class="blocked-name">{name}</span>'
            f'<span class="blocked-reason">{reason}</span>'
            f"</li>"
        )

    return f'<ul class="blocked-list">{"".join(rows)}</ul>'


def _html_section_body(items: list[dict], *, section_key: str) -> str:
    if not items:
        return '<p class="section-empty">Nothing on the board yet.</p>'

    groups = _group_items_by_market(items)
    blocks: list[str] = []
    for _market_key, group_items in groups:
        market_short = group_items[0].get("market_short", "")
        tilt = float(group_items[0].get("tilt", -1.5))
        rows = [
            _html_price_row(item, section_key=section_key, grouped_by_market=True)
            for item in group_items
        ]
        wide = len(group_items) > 5
        group_cls = "market-group market-group--wide" if wide else "market-group"
        blocks.append(
            f'<div class="{group_cls}">'
            f"{_html_market_sign(market_short, section_key=section_key, tilt=tilt)}"
            f'<ul class="price-list">{"".join(rows)}</ul>'
            f"</div>"
        )
    return f'<div class="market-groups">{"".join(blocks)}</div>'


def render_chalk_html(board: dict) -> str:
    is_demo = board.get("is_demo", False)
    demo_banner = (
        '<p class="demo-banner">Demo board — run scrape for live prices</p>' if is_demo else ""
    )

    sections_html: list[str] = []
    for section_key in ("lobster", "oyster", "special"):
        emoji, heading, _ = _SECTION_META[section_key]
        items = board["sections"].get(section_key, [])
        body = _html_section_body(items, section_key=section_key)
        sections_html.append(
            f'<section class="board-section section-{section_key}">'
            f'<h2 class="section-heading">{emoji} {html.escape(heading)}</h2>'
            f"{body}"
            f"</section>"
        )

    trends_html = ""
    trends = board.get("trends", {})
    if trends and trends.get("labels"):
        trends_html = (
            '<section class="board-section section-trends">'
            '<h2 class="section-heading">📈 Price Trends</h2>'
            '<div class="chart-container">'
            '<canvas id="trendsChart"></canvas>'
            "</div>"
            "</section>"
        )
        sections_html.append(trends_html)

    coverage = board.get("market_coverage") or []
    live_n = board.get("live_market_count", sum(1 for c in coverage if c["status"] == "live"))
    blocked_n = board.get(
        "blocked_market_count", sum(1 for c in coverage if c["status"] == "blocked")
    )
    partial_n = board.get(
        "partial_market_count", sum(1 for c in coverage if c["status"] == "partial")
    )
    unavailable_n = blocked_n + partial_n
    summary = board.get("coverage_summary") or f"{live_n} live · {unavailable_n} awaiting feed"
    updated = html.escape(_format_observed(board.get("updated_at", "")))
    blocked_details = _html_blocked_details(coverage)

    footer_extra = ""
    if blocked_details:
        footer_extra = (
            f'<details class="markets-details">'
            f"<summary>{html.escape(summary)}</summary>"
            f"{blocked_details}"
            f"</details>"
        )
    else:
        footer_extra = f'<p class="footer-summary">{html.escape(summary)}</p>'

    if is_demo:
        footer_line = f'<p class="footer-meta">Updated {updated}</p>'
    else:
        footer_line = f'<p class="footer-meta">Updated {updated}</p>'

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(board["title"])}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Caveat:wght@500;600;700&display=swap" rel="stylesheet">
  <style>
    /* --- Design tokens (mobile-first) --- */
    :root {{
      --board-bg: #0c1612;
      --board-mid: #142820;
      --chalk: #f2ead8;
      --chalk-dim: #b8aa94;
      --chalk-muted: #8a7d6a;
      --lobster: #ff8a78;
      --ocean: #8ec8e8;
      --gold: #e8c84a;
      --frame: #4a3418;
      --frame-max: min(480px, 100%);
      --logo-size: clamp(4rem, 12vw, 5.5rem);
      --space-xs: 0.25rem;
      --space-sm: 0.5rem;
      --space-md: 0.75rem;
      --space-lg: 1rem;
      --space-xl: 1.5rem;
      --board-pad-y: var(--space-lg);
      --board-pad-x: var(--space-lg);
      --section-gap: var(--space-xl);
      --group-gap: var(--space-lg);
      --row-pad-y: 0.7rem;
      --text-heading: clamp(1.3rem, 4.5vw, 1.55rem);
      --text-row: clamp(1.15rem, 3.8vw, 1.35rem);
      --text-price: clamp(1.45rem, 5.5vw, 2rem);
      --price-col-min: 5.5rem;
    }}
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      min-height: 100vh;
      background: #060a08;
      display: flex;
      justify-content: center;
      padding: var(--space-sm);
      font-family: 'Caveat', cursive;
      color: var(--chalk);
      -webkit-font-smoothing: antialiased;
      overflow-x: hidden;
    }}
    .board-frame {{
      width: 100%;
      max-width: var(--frame-max);
      background: linear-gradient(165deg, #6a4a20, var(--frame));
      border-radius: 8px;
      padding: 10px;
      box-shadow: 0 20px 60px rgba(0,0,0,.65);
    }}
    .board {{
      background: linear-gradient(180deg, var(--board-mid) 0%, var(--board-bg) 100%);
      border: 3px solid #08100c;
      border-radius: 4px;
      padding: var(--board-pad-y) var(--board-pad-x) var(--space-lg);
      min-height: 70vh;
    }}
    header {{
      text-align: center;
      margin-bottom: var(--space-xl);
      padding-bottom: var(--space-md);
      border-bottom: 1px solid rgba(242,234,216,.12);
    }}
    h1 {{
      font-size: clamp(1.45rem, 6vw, 2rem);
      font-weight: 700;
      letter-spacing: 0.03em;
      line-height: 1.15;
      color: var(--chalk);
      word-break: break-word;
    }}
    .subtitle {{
      font-size: 1.05rem;
      color: var(--chalk-dim);
      margin-top: var(--space-xs);
      line-height: 1.4;
    }}
    .date {{
      font-size: 1.1rem;
      font-weight: 600;
      color: var(--gold);
      margin-top: var(--space-xs);
    }}
    .demo-banner {{
      text-align: center;
      font-size: 1rem;
      color: var(--gold);
      margin-bottom: var(--space-lg);
      opacity: 0.9;
    }}
    .board-section {{
      margin-bottom: var(--section-gap);
    }}
    .board-section:last-child {{
      margin-bottom: 0;
    }}
    .section-heading {{
      font-size: var(--text-heading);
      font-weight: 700;
      margin-bottom: var(--space-md);
      padding-bottom: var(--space-sm);
      border-bottom: 2px solid currentColor;
      letter-spacing: 0.05em;
      line-height: 1.2;
      text-transform: uppercase;
    }}
    .section-lobster .section-heading {{ color: var(--lobster); }}
    .section-oyster .section-heading {{ color: var(--ocean); }}
    .section-special .section-heading {{ color: var(--gold); }}
    .section-trends .section-heading {{ color: var(--chalk-dim); border-color: rgba(242,234,216,.2); }}
    .chart-container {{
      position: relative;
      height: 180px;
      width: 100%;
      margin-top: var(--space-sm);
      border-bottom: 1px solid rgba(242,234,216,.08);
      padding-bottom: var(--space-lg);
    }}
    .market-groups {{
      display: flex;
      flex-direction: column;
      gap: var(--group-gap);
      overflow: visible;
    }}
    .market-group {{
      display: flex;
      flex-direction: column;
      gap: var(--space-xs);
    }}
    .market-sign {{
      display: flex;
      justify-content: center;
      align-items: center;
      margin: var(--space-xs) 0 var(--space-sm);
      padding: 0 var(--space-xs);
    }}
    .market-sign-logo {{
      width: var(--logo-size);
      height: var(--logo-size);
      border-radius: 50%;
      object-fit: cover;
      flex-shrink: 0;
      border: 2px solid rgba(0,0,0,.35);
      box-shadow: 0 2px 8px rgba(0,0,0,.4);
    }}
    .market-sign-label {{
      font-size: clamp(1.1rem, 4.5vw, 1.3rem);
      font-weight: 700;
      letter-spacing: 0.05em;
      line-height: 1.2;
      text-align: center;
      text-shadow: 0 1px 2px rgba(0,0,0,.35);
    }}
    .section-lobster .market-sign-label {{ color: var(--lobster); }}
    .section-oyster .market-sign-label {{ color: var(--ocean); }}
    .section-special .market-sign-label {{ color: var(--gold); }}
    .price-list {{
      list-style: none;
      display: flex;
      flex-direction: column;
    }}
    .price-row {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      align-items: baseline;
      gap: var(--space-xs) var(--space-md);
      padding: var(--row-pad-y) 0;
      border-bottom: 1px solid rgba(242,234,216,.08);
      line-height: 1.3;
    }}
    .price-row:last-child {{ border-bottom: none; }}
    .row-left {{
      display: flex;
      flex-direction: column;
      gap: 0.05rem;
      min-width: 0;
    }}
    .row-primary {{
      font-size: var(--text-row);
      font-weight: 700;
      color: var(--chalk);
      line-height: 1.25;
    }}
    .row-secondary {{
      font-size: clamp(0.95rem, 3.2vw, 1.1rem);
      font-weight: 600;
      color: var(--chalk-dim);
      line-height: 1.25;
    }}
    .row-subtext {{
      display: inline-block;
      font-size: 0.72em;
      font-weight: 500;
      color: var(--chalk-muted);
      margin-left: 0.3em;
      letter-spacing: 0.02em;
      opacity: 0.75;
      vertical-align: baseline;
    }}
    .row-price {{
      text-align: right;
      white-space: nowrap;
      min-width: var(--price-col-min);
    }}
    .section-lobster .price-amount {{ color: var(--lobster); }}
    .section-oyster .price-amount {{ color: var(--ocean); }}
    .section-special .price-amount {{ color: var(--gold); }}
    .price-amount {{
      font-size: var(--text-price);
      font-weight: 700;
      letter-spacing: -0.02em;
      font-variant-numeric: tabular-nums;
    }}
    .price-unit {{
      font-size: 0.72em;
      font-weight: 600;
      color: var(--chalk-dim);
      margin-left: 0.08em;
    }}
    .row-price.is-out .price-amount {{
      color: var(--chalk-muted);
    }}
    .price-amount.is-wide {{
      font-size: clamp(1.2rem, 4.5vw, 1.55rem);
      white-space: normal;
      max-width: 8.5rem;
    }}
    .price-row.is-consolidated .row-primary {{
      font-size: clamp(1.05rem, 3.5vw, 1.25rem);
    }}
    .section-empty {{
      font-size: 1.1rem;
      color: var(--chalk-muted);
      font-style: italic;
      padding: var(--space-sm) 0;
    }}
    footer {{
      margin-top: var(--space-xl);
      padding-top: var(--space-lg);
      border-top: 1px solid rgba(242,234,216,.1);
      text-align: center;
    }}
    .markets-details {{ text-align: left; }}
    .markets-details summary {{
      font-size: 1.05rem;
      font-weight: 600;
      color: var(--chalk-dim);
      cursor: pointer;
      list-style: none;
      text-align: center;
      line-height: 1.5;
      padding: var(--space-xs) 0;
    }}
    .markets-details summary::-webkit-details-marker {{ display: none; }}
    .markets-details[open] summary {{
      margin-bottom: var(--space-md);
      color: var(--chalk);
    }}
    .markets-details summary::after {{
      content: " ▾";
      font-size: 0.85em;
      opacity: 0.7;
    }}
    .markets-details[open] summary::after {{ content: " ▴"; }}
    .footer-summary {{
      font-size: 1.05rem;
      font-weight: 600;
      color: var(--chalk-dim);
      line-height: 1.5;
    }}
    .footer-meta {{
      font-size: 0.95rem;
      color: var(--chalk-muted);
      margin-top: var(--space-sm);
      line-height: 1.4;
    }}
    .blocked-list {{
      list-style: none;
      display: flex;
      flex-direction: column;
      gap: var(--space-sm);
    }}
    .blocked-item {{
      display: flex;
      flex-direction: column;
      gap: 0.1rem;
      padding: var(--space-sm) 0.65rem;
      background: rgba(0,0,0,.2);
      border-radius: 4px;
      line-height: 1.35;
    }}
    .blocked-name {{
      font-size: 1.05rem;
      font-weight: 700;
      color: var(--chalk-dim);
    }}
    .blocked-reason {{
      font-size: 0.9rem;
      color: var(--chalk-muted);
    }}

    /* --- Breakpoint: mobile (≤480px) --- */
    @media (max-width: 480px) {{
      body {{ padding: var(--space-sm); }}
      .board-frame {{ padding: 8px; }}
      .board {{ padding: var(--space-lg) 0.85rem; }}
      h1 {{ font-size: 1.5rem; }}
      .price-row {{
        grid-template-columns: 1fr;
        gap: 0.15rem;
      }}
      .row-price {{
        text-align: left;
        min-width: 0;
        white-space: normal;
      }}
      .price-row.is-consolidated {{
        grid-template-columns: minmax(0, 1fr) auto;
        align-items: center;
      }}
      .price-row.is-consolidated .row-price {{
        text-align: right;
        min-width: var(--price-col-min);
        white-space: nowrap;
      }}
    }}

    /* --- Breakpoint: tablet (≥481px) --- */
    @media (min-width: 481px) {{
      .price-row {{
        grid-template-columns: minmax(0, 1fr) auto;
        align-items: baseline;
      }}
    }}

    /* --- Breakpoint: desktop (≥768px) --- */
    @media (min-width: 768px) {{
      :root {{
        --frame-max: min(900px, 100%);
        --logo-size: clamp(5rem, 6vw, 6rem);
        --board-pad-y: var(--space-xl);
        --board-pad-x: 1.25rem;
        --section-gap: 0;
        --group-gap: var(--space-md);
        --row-pad-y: 0.45rem;
        --text-row: 1.15rem;
        --text-price: 1.65rem;
        --price-col-min: 5rem;
      }}
      body {{ padding: var(--space-lg); }}
      .board-body {{
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: var(--space-lg) 1.5rem;
        align-items: start;
      }}
      .board-section {{
        display: flex;
        flex-direction: column;
        min-width: 0;
        margin-bottom: 0;
      }}
      .section-special,
      .section-trends {{
        grid-column: 1 / -1;
        margin-top: var(--space-md);
      }}
      .section-special .market-groups {{
        columns: 3;
        column-gap: var(--space-lg);
        align-items: start;
      }}
      .section-special .market-group {{
        break-inside: avoid;
        -webkit-column-break-inside: avoid;
        page-break-inside: avoid;
        display: inline-block;
        width: 100%;
        margin-bottom: var(--space-sm);
      }}
      .section-special .market-group--wide .price-list {{
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        column-gap: var(--space-md);
      }}
      .section-special .row-primary {{
        font-size: 1.05rem;
        line-height: 1.2;
      }}
      .section-special .price-amount {{
        font-size: 1.35rem;
      }}
      .section-special .price-amount.is-wide {{
        font-size: 1.1rem;
      }}
    }}

    /* --- Breakpoint: wide desktop (≥1024px) — one-screen board --- */
    @media (min-width: 1024px) {{
      :root {{
        --frame-max: min(1050px, 100%);
        --logo-size: clamp(5rem, 6vw, 6rem);
        --board-pad-y: 0.75rem;
        --board-pad-x: 1rem;
        --group-gap: 0.35rem;
        --row-pad-y: 0.22rem;
        --text-heading: 1.15rem;
        --text-row: 1rem;
        --text-price: 1.25rem;
        --price-col-min: 4.25rem;
      }}
      body {{ padding: 0.35rem 0.6rem; }}
      .board {{
        min-height: unset;
        padding-bottom: 0.5rem;
      }}
      header {{
        margin-bottom: 0.45rem;
        padding-bottom: 0.3rem;
      }}
      h1 {{ font-size: 1.65rem; }}
      .subtitle {{ font-size: 0.88rem; margin-top: 0.05rem; }}
      .date {{ font-size: 0.92rem; }}
      .board-body {{
        gap: 0.35rem 0.85rem;
      }}
      .section-heading {{
        margin-bottom: 0.2rem;
        padding-bottom: 0.15rem;
        font-size: var(--text-heading);
      }}
      .section-special {{
        margin-top: 0.25rem;
      }}
      .section-lobster .market-groups {{
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 0.3rem 0.5rem;
        align-items: start;
      }}
      .section-oyster .market-groups {{
        display: grid;
        grid-template-columns: 1fr;
        gap: 0.3rem;
      }}
      .section-special .market-groups {{
        columns: 3;
        column-gap: 0.65rem;
        align-items: start;
      }}
      .section-special .market-group {{
        break-inside: avoid;
        -webkit-column-break-inside: avoid;
        page-break-inside: avoid;
        display: inline-block;
        width: 100%;
        margin-bottom: 0.25rem;
      }}
      .market-sign {{
        margin: 0.05rem 0 0.1rem;
      }}
      .section-special .row-primary {{
        font-size: 0.92rem;
        line-height: 1.15;
      }}
      .section-special .row-subtext {{
        font-size: 0.68em;
      }}
      .section-special .price-row {{
        padding: 0.12rem 0;
      }}
      .section-special .price-amount {{
        font-size: 1.1rem;
      }}
      .section-special .price-amount.is-wide {{
        font-size: 0.92rem;
        max-width: 6.5rem;
      }}
      .section-special .market-group--wide .price-list {{
        column-gap: 0.5rem;
      }}
      .chart-container {{
        height: 90px;
        margin-top: 0.15rem;
        padding-bottom: 0.4rem;
      }}
      footer {{
        margin-top: 0.35rem;
        padding-top: 0.35rem;
      }}
      .footer-summary,
      .markets-details summary {{ font-size: 0.88rem; }}
      .footer-meta {{
        font-size: 0.78rem;
        margin-top: 0.15rem;
      }}
    }}
  </style>
</head>
<body>
  <div class="board-frame">
    <div class="board">
      <header>
        <h1>{html.escape(board["title"])}</h1>
        <p class="subtitle">{html.escape(board["subtitle"])}</p>
        <p class="date">{html.escape(board.get("display_date", ""))}</p>
      </header>
      {demo_banner}
      <div class="board-body">
        {"".join(sections_html)}
      </div>
      <footer>
        {footer_extra}
        {footer_line}
      </footer>
    </div>
  </div>
</body>
</html>"""

    script_content = f"""
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
  <script>
    (function() {{
      const ctx = document.getElementById('trendsChart');
      if (!ctx) return;
      const trends = {json.dumps(board.get("trends", {}))};

      new Chart(ctx, {{
        type: 'line',
        data: {{
          labels: trends.labels || [],
          datasets: [
            {{
              label: 'Soft Shell ($/lb)',
              data: trends.soft_shell || [],
              borderColor: '#ff8a78', // var(--lobster)
              backgroundColor: 'rgba(255, 138, 120, 0.1)',
              borderWidth: 2,
              tension: 0.15,
              spanGaps: true,
              pointBackgroundColor: '#ff8a78',
              pointRadius: 3
            }},
            {{
              label: 'Hard Shell ($/lb)',
              data: trends.hard_shell || [],
              borderColor: '#8ec8e8', // var(--ocean)
              backgroundColor: 'rgba(142, 200, 232, 0.1)',
              borderWidth: 2,
              tension: 0.15,
              spanGaps: true,
              pointBackgroundColor: '#8ec8e8',
              pointRadius: 3
            }}
          ]
        }},
        options: {{
          responsive: true,
          maintainAspectRatio: false,
          plugins: {{
            legend: {{
              labels: {{
                color: '#f2ead8', // var(--chalk)
                font: {{
                  family: "'Caveat', cursive",
                  size: 14
                }}
              }}
            }}
          }},
          scales: {{
            x: {{
              grid: {{
                color: 'rgba(242, 234, 216, 0.08)'
              }},
              ticks: {{
                color: '#b8aa94', // var(--chalk-dim)
                font: {{
                  family: "'Caveat', cursive",
                  size: 12
                }}
              }}
            }},
            y: {{
              grid: {{
                color: 'rgba(242, 234, 216, 0.08)'
              }},
              ticks: {{
                color: '#b8aa94',
                font: {{
                  family: "'Caveat', cursive",
                  size: 12
                }},
                callback: function(value) {{
                  return '$' + value;
                }}
              }}
            }}
          }}
        }}
      }});
    }})();
  </script>
</body>
</html>"""

    return html_content.replace("</body>\n</html>", script_content)
