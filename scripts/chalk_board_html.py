"""Clean, scannable chalkboard HTML — mobile-first price list."""

from __future__ import annotations

import html
import json

from board_render import _SECTION_META, _format_observed


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
    label = str(item.get("label") or "")
    if section_key == "oyster" and label.lower() == "oysters":
        return "per dozen"
    return label


def _html_market_sign(market_short: str, *, section_key: str, tilt: float) -> str:
    name = html.escape(market_short)
    return (
        f'<div class="market-sign section-{section_key}" style="--sign-tilt: {tilt:.1f}deg">'
        f'<span class="market-sign-frame">'
        f'<span class="market-sign-board">{name}</span>'
        f"</span>"
        f"</div>"
    )


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
        left_secondary = "per dozen" if label.lower() == "oysters" else label
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
        f'<span class="row-primary">{left_primary}</span>'
        f"{secondary_html}"
        f"{sub_html}"
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
        blocks.append(
            f'<div class="market-group">'
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
            '<div class="chart-container" style="position: relative; height: 180px; width: 100%; margin-top: 0.5rem; border-bottom: 1px solid rgba(242,234,216,.08); padding-bottom: 1.5rem;">'
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
    }}
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      min-height: 100vh;
      background: #060a08;
      display: flex;
      justify-content: center;
      padding: 0.75rem;
      font-family: 'Caveat', cursive;
      color: var(--chalk);
      -webkit-font-smoothing: antialiased;
      overflow-x: hidden;
    }}
    .board-frame {{
      width: 100%;
      max-width: min(480px, 100%);
      background: linear-gradient(165deg, #6a4a20, var(--frame));
      border-radius: 8px;
      padding: 10px;
      box-shadow: 0 20px 60px rgba(0,0,0,.65);
    }}
    .board {{
      background: linear-gradient(180deg, var(--board-mid) 0%, var(--board-bg) 100%);
      border: 3px solid #08100c;
      border-radius: 4px;
      padding: 1.25rem 1rem 1rem;
      min-height: 70vh;
    }}
    header {{
      text-align: center;
      margin-bottom: 1.5rem;
      padding-bottom: 0.75rem;
      border-bottom: 1px solid rgba(242,234,216,.12);
    }}
    h1 {{
      font-size: clamp(1.45rem, 6vw, 2.1rem);
      font-weight: 700;
      letter-spacing: 0.03em;
      line-height: 1.15;
      color: var(--chalk);
      word-break: break-word;
    }}
    .subtitle {{
      font-size: 1.05rem;
      color: var(--chalk-dim);
      margin-top: 0.35rem;
      line-height: 1.4;
    }}
    .date {{
      font-size: 1.15rem;
      font-weight: 600;
      color: var(--gold);
      margin-top: 0.25rem;
    }}
    .demo-banner {{
      text-align: center;
      font-size: 1rem;
      color: var(--gold);
      margin-bottom: 1rem;
      opacity: 0.9;
    }}
    .board-section {{
      margin-bottom: 1.75rem;
    }}
    .section-heading {{
      font-size: clamp(1.35rem, 5vw, 1.6rem);
      font-weight: 700;
      margin-bottom: 0.75rem;
      letter-spacing: 0.03em;
      line-height: 1.3;
    }}
    .section-lobster .section-heading {{ color: var(--lobster); }}
    .section-oyster .section-heading {{ color: var(--ocean); }}
    .section-special .section-heading {{ color: var(--gold); }}
    .market-groups {{
      display: flex;
      flex-direction: column;
      gap: 1.35rem;
    }}
    .market-group {{
      display: flex;
      flex-direction: column;
      gap: 0.15rem;
    }}
    .market-sign {{
      display: flex;
      justify-content: center;
      margin: 0.15rem 0 0.35rem;
      padding: 0 0.25rem;
    }}
    .market-sign-frame {{
      display: inline-block;
      transform: rotate(var(--sign-tilt, -1.5deg));
      background: linear-gradient(165deg, #7a5628 0%, #5c3f18 45%, var(--frame) 100%);
      padding: 5px 7px;
      border-radius: 5px;
      box-shadow:
        0 4px 10px rgba(0,0,0,.45),
        inset 0 1px 0 rgba(255,255,255,.12),
        inset 0 -1px 0 rgba(0,0,0,.25);
    }}
    .market-sign-board {{
      display: block;
      min-width: 7.5rem;
      text-align: center;
      background:
        linear-gradient(180deg, rgba(255,255,255,.04) 0%, transparent 40%),
        linear-gradient(180deg, var(--board-mid) 0%, var(--board-bg) 100%);
      border: 2px solid #08100c;
      border-radius: 3px;
      padding: 0.3rem 1.1rem;
      font-size: clamp(1.05rem, 4.2vw, 1.3rem);
      font-weight: 700;
      color: var(--chalk);
      letter-spacing: 0.05em;
      line-height: 1.2;
      text-shadow: 0 1px 2px rgba(0,0,0,.35);
      box-shadow: inset 0 2px 6px rgba(0,0,0,.28);
    }}
    .section-lobster .market-sign-board {{ color: var(--lobster); }}
    .section-oyster .market-sign-board {{ color: var(--ocean); }}
    .section-special .market-sign-board {{ color: var(--gold); }}
    .market-group .price-list {{
      padding: 0 0.15rem;
    }}
    .market-group .price-row:first-child {{
      padding-top: 0.55rem;
    }}
    .market-group .price-row:last-child {{
      border-bottom: none;
    }}
    .market-group:not(:last-child) {{
      padding-bottom: 0.35rem;
      border-bottom: 1px dashed rgba(242,234,216,.06);
    }}
    .price-list {{
      list-style: none;
      display: flex;
      flex-direction: column;
      gap: 0;
    }}
    .price-row {{
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      flex-wrap: wrap;
      gap: 0.35rem 0.5rem;
      padding: 0.85rem 0;
      border-bottom: 1px solid rgba(242,234,216,.08);
      line-height: 1.35;
    }}
    .price-row:last-child {{ border-bottom: none; }}
    .row-left {{
      display: flex;
      flex-direction: column;
      gap: 0.1rem;
      min-width: 0;
      flex: 1;
    }}
    .row-primary {{
      font-size: clamp(1.2rem, 4.5vw, 1.45rem);
      font-weight: 700;
      color: var(--chalk);
      line-height: 1.25;
    }}
    .row-secondary {{
      font-size: clamp(1rem, 3.5vw, 1.15rem);
      font-weight: 600;
      color: var(--chalk-dim);
      line-height: 1.3;
    }}
    .row-subtext {{
      font-size: 0.95rem;
      font-weight: 500;
      color: var(--chalk-muted);
      margin-top: 0.15rem;
      line-height: 1.35;
    }}
    .row-price {{
      flex: 0 0 auto;
      text-align: right;
      white-space: normal;
      line-height: 1.1;
      max-width: 100%;
    }}
    .section-lobster .price-amount {{ color: var(--lobster); }}
    .section-oyster .price-amount {{ color: var(--ocean); }}
    .section-special .price-amount {{ color: var(--gold); }}
    .price-amount {{
      font-size: clamp(1.5rem, 6.5vw, 2.25rem);
      font-weight: 700;
      letter-spacing: -0.01em;
    }}
    .price-unit {{
      font-size: 1.1rem;
      font-weight: 600;
      color: var(--chalk-dim);
      margin-left: 0.1em;
    }}
    .row-price.is-out .price-amount {{
      color: var(--chalk-muted);
    }}
    .section-empty {{
      font-size: 1.1rem;
      color: var(--chalk-muted);
      font-style: italic;
      padding: 0.5rem 0;
    }}
    footer {{
      margin-top: 1.5rem;
      padding-top: 1rem;
      border-top: 1px solid rgba(242,234,216,.1);
      text-align: center;
    }}
    .markets-details {{
      text-align: left;
    }}
    .markets-details summary {{
      font-size: 1.05rem;
      font-weight: 600;
      color: var(--chalk-dim);
      cursor: pointer;
      list-style: none;
      text-align: center;
      line-height: 1.5;
      padding: 0.25rem 0;
    }}
    .markets-details summary::-webkit-details-marker {{ display: none; }}
    .markets-details[open] summary {{
      margin-bottom: 0.75rem;
      color: var(--chalk);
    }}
    .footer-summary {{
      font-size: 1.05rem;
      font-weight: 600;
      color: var(--chalk-dim);
      line-height: 1.5;
    }}
    .footer-meta {{
      font-size: 0.95rem;
      color: var(--chalk-muted);
      margin-top: 0.5rem;
      line-height: 1.4;
    }}
    .blocked-list {{
      list-style: none;
      display: flex;
      flex-direction: column;
      gap: 0.5rem;
    }}
    .blocked-item {{
      display: flex;
      flex-direction: column;
      gap: 0.1rem;
      padding: 0.5rem 0.65rem;
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
    .price-row.is-consolidated .row-secondary {{
      font-size: clamp(0.95rem, 3.2vw, 1.1rem);
      color: var(--chalk-dim);
      letter-spacing: 0.01em;
    }}
    .price-amount.is-wide {{
      font-size: clamp(1.35rem, 5.5vw, 1.75rem);
    }}
    .markets-details summary::after {{
      content: " ▾";
      font-size: 0.85em;
      opacity: 0.7;
    }}
    .markets-details[open] summary::after {{
      content: " ▴";
    }}
    @media (min-width: 481px) {{
      .price-row {{
        flex-wrap: nowrap;
        align-items: center;
        gap: 0.75rem;
      }}
      .row-price {{
        flex-shrink: 0;
      }}
    }}
    @media (min-width: 768px) {{
      body {{
        padding: 1rem 1.25rem;
      }}
      .board-frame {{
        max-width: min(900px, 100%);
      }}
      .board {{
        padding: 1.5rem 1.35rem 1.25rem;
      }}
      .board-body {{
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 1.5rem 2rem;
        align-items: start;
      }}
      .board-section {{
        margin-bottom: 0;
      }}
      .section-special,
      .section-trends {{
        grid-column: 1 / -1;
      }}
      .section-special .market-groups {{
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 1.25rem 1.5rem;
      }}
      .section-special .market-group:not(:last-child) {{
        border-bottom: none;
        padding-bottom: 0;
      }}
    }}
    @media (min-width: 1024px) {{
      .board-frame {{
        max-width: min(1050px, 100%);
      }}
      .board-body {{
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 1.25rem 1.75rem;
      }}
      .section-special {{
        grid-column: auto;
      }}
      .section-trends {{
        grid-column: 1 / -1;
      }}
      .section-special .market-groups {{
        grid-template-columns: 1fr;
      }}
    }}
    @media (max-width: 480px) {{
      body {{ padding: 0.5rem; }}
      .board-frame {{ padding: 8px; }}
      .board {{ padding: 1rem 0.85rem; }}
      h1 {{
        font-size: 1.55rem;
        letter-spacing: 0.02em;
        word-break: break-word;
      }}
      .price-row {{
        flex-wrap: wrap;
        align-items: flex-start;
        gap: 0.35rem 0.5rem;
        padding: 0.75rem 0;
      }}
      .row-price {{
        flex: 0 0 100%;
        text-align: left;
        white-space: normal;
        padding-left: 0.1rem;
      }}
      .price-amount {{ font-size: 1.75rem; }}
      .price-amount.is-wide {{ font-size: 1.4rem; }}
      .price-row.is-consolidated .price-amount {{ font-size: 1.55rem; }}
      .price-row.is-consolidated {{
        flex-wrap: nowrap;
        align-items: center;
        gap: 0.5rem;
      }}
      .price-row.is-consolidated .row-left {{
        flex: 1 1 auto;
        min-width: 0;
      }}
      .price-row.is-consolidated .row-price {{
        flex: 0 0 auto;
        text-align: right;
        padding-left: 0;
      }}
      .price-row.is-consolidated .row-secondary {{
        font-size: 0.95rem;
      }}
      .market-sign-frame {{
        max-width: calc(100% - 1rem);
      }}
      .market-sign-board {{
        min-width: 0;
        max-width: 100%;
        padding: 0.28rem 0.85rem;
        font-size: 1.05rem;
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
