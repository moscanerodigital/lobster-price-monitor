"""Seafood board rendering — chalkboard-style terminal, HTML, and Telegram."""
from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from pathlib import Path

from state import read_jsonl, DATA_DIR

# Friendly labels for canonical keys
_ITEM_LABELS: dict[str, str] = {
    "chicks": "Chicks",
    "soft_shell": "Soft Shell",
    "old_shell": "Old Shell",
    "hard_shell": "Hard Shell",
    "select": "Select",
    "1.125lb": "1⅛ lb",
    "1.25lb": "1¼ lb",
    "1.5lb": "1½ lb",
    "1.75lb": "1¾ lb",
    "2lb_plus": "2 lb+",
    "1lb": "1 lb",
    "xl": "Extra Large",
    "jumbo": "Jumbo",
    "standard": "Standard",
    "single_select": "Single Select",
    "named_variety": "Named Variety",
    "oyster": "Oysters",
    "lobster_roll": "Lobster Roll",
    "halibut": "Halibut",
    "scallops": "Scallops",
    "clams": "Clams",
    "shrimp": "Shrimp",
    "haddock": "Haddock",
    "salmon": "Salmon",
    "chowder": "Chowder",
    "bisque": "Bisque",
    "crab": "Crab",
}

_SECTION_META = {
    "lobster": ("🦞", "LIVE LOBSTER", "lb"),
    "oyster": ("🦪", "OYSTERS", "doz"),
    "special": ("🐟", "TODAY'S CATCH", ""),
}


def _parse_ts(s: str) -> datetime | None:
    if not s:
        return None
    s = s.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _is_today(ts: str) -> bool:
    dt = _parse_ts(ts)
    if not dt:
        return False
    return dt.astimezone(timezone.utc).date() == datetime.now(timezone.utc).date()


def label_for(key: str) -> str:
    if key in _ITEM_LABELS:
        return _ITEM_LABELS[key]
    return re.sub(r"_+", " ", key).strip().title()


def short_market(name: str) -> str:
    """Abbreviate long market names for the board."""
    shortcuts = {
        "Ancient Mariner Lobster Co.": "Ancient Mariner",
        "Pine Tree Seafood & Produce": "Pine Tree",
        "Harbor Fish Market (Oysters)": "Harbor Fish",
        "Scarborough Fish & Lobster": "Scarborough F&L",
        "Free Range Fish & Lobster": "Free Range",
        "SoPo Seafood Market & Raw Bar": "SoPo Seafood",
        "Two Tides Seafood": "Two Tides",
    }
    return shortcuts.get(name, name.split("(")[0].strip()[:22])


def format_price(price: float, unit: str) -> str:
    if unit == "ea":
        return f"${price:.2f} ea"
    if unit == "doz":
        return f"${price:.2f}/doz"
    return f"${price:.2f}/lb"


def load_board_rows(
    *,
    min_confidence: int = 70,
    today_only: bool = False,
    market: str | None = None,
) -> list[dict]:
    rows = read_jsonl("prices.jsonl")
    out: list[dict] = []
    for r in rows:
        if r.get("gate_passed") is False:
            continue
        conf = int(r.get("confidence", 0))
        if conf < min_confidence:
            continue
        if market and market.lower() not in r.get("market", "").lower():
            continue
        observed = r.get("observed_at", "")
        if today_only and not _is_today(observed):
            continue
        out.append(r)
    return out


def build_board(
    *,
    min_confidence: int = 70,
    today_only: bool = False,
    market: str | None = None,
) -> dict:
    """Group gated prices into board sections."""
    rows = load_board_rows(
        min_confidence=min_confidence, today_only=today_only, market=market,
    )
    sections: dict[str, list[dict]] = {
        "lobster": [],
        "oyster": [],
        "special": [],
    }
    latest_ts = ""
    for r in rows:
        kind = r.get("kind", "")
        if kind == "lobster_tier":
            bucket = "lobster"
        elif kind == "oyster_tier":
            bucket = "oyster"
        elif kind == "special":
            bucket = "special"
        else:
            continue
        item = {
            "label": label_for(r.get("key", "?")),
            "key": r.get("key", ""),
            "price": float(r.get("price", 0)),
            "unit": r.get("unit", "lb"),
            "price_str": format_price(float(r.get("price", 0)), r.get("unit", "lb")),
            "market": r.get("market", "?"),
            "market_short": short_market(r.get("market", "?")),
            "confidence": int(r.get("confidence", 0)),
            "observed_at": r.get("observed_at", ""),
        }
        sections[bucket].append(item)
        if r.get("observed_at", "") > latest_ts:
            latest_ts = r.get("observed_at", "")

    for key in sections:
        sections[key].sort(key=lambda x: (x["market_short"], x["label"], x["price"]))

    now = datetime.now(timezone.utc)
    return {
        "title": "MAINE COAST SEAFOOD BOARD",
        "subtitle": "Gorham · 15 mi coastal radius",
        "updated_at": latest_ts or now.isoformat(),
        "display_date": now.strftime(f"%A, %B {now.day}"),
        "sections": sections,
        "total_items": sum(len(v) for v in sections.values()),
    }


def _demo_board() -> dict:
    """Sample board when no prices.jsonl exists yet."""
    now = datetime.now(timezone.utc).isoformat()
    return {
        "title": "MAINE COAST SEAFOOD BOARD",
        "subtitle": "Gorham · 15 mi coastal radius",
        "updated_at": now,
        "display_date": datetime.now(timezone.utc).strftime("%A, %B %d"),
        "sections": {
            "lobster": [
                {"label": "Chicks", "price_str": "$8.75/lb", "market_short": "Ancient Mariner", "confidence": 85},
                {"label": "Hard Shell", "price_str": "$11.95/lb", "market_short": "Ancient Mariner", "confidence": 88},
                {"label": "1¼ lb", "price_str": "$9.99/lb", "market_short": "Two Tides", "confidence": 82},
            ],
            "oyster": [
                {"label": "Wellfleet Select", "price_str": "$24.00/doz", "market_short": "Harbor Fish", "confidence": 90},
                {"label": "XL Kumamoto", "price_str": "$32.00/doz", "market_short": "Harbor Fish", "confidence": 87},
            ],
            "special": [
                {"label": "Lobster Roll", "price_str": "$24.99 ea", "market_short": "Pine Tree", "confidence": 78},
                {"label": "Halibut", "price_str": "$18.99/lb", "market_short": "Harbor Fish", "confidence": 81},
                {"label": "Scallops", "price_str": "$22.99/lb", "market_short": "Scarborough F&L", "confidence": 76},
            ],
        },
        "total_items": 8,
        "is_demo": True,
    }


def get_board(*, demo: bool = False, **kwargs) -> dict:
    if demo or not (DATA_DIR / "prices.jsonl").exists():
        real = build_board(**kwargs)
        if real["total_items"] == 0 and (demo or not (DATA_DIR / "prices.jsonl").exists()):
            return _demo_board()
        return real
    board = build_board(**kwargs)
    return board if board["total_items"] else _demo_board()


# ---- Terminal (ANSI chalkboard) ----

ANSI = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[2m",
    "bg": "\033[48;5;236m",
    "chalk": "\033[38;5;252m",
    "lobster": "\033[38;5;203m",
    "ocean": "\033[38;5;39m",
    "gold": "\033[38;5;220m",
    "rope": "\033[38;5;130m",
}


def render_terminal(board: dict, *, width: int = 62) -> str:
    a = ANSI
    lines: list[str] = []
    w = width

    def bar(char: str = "─") -> str:
        return f"{a['rope']}{char * (w - 2)}{a['reset']}"

    lines.append(f"{a['bg']}{a['rope']}╔{'═' * (w - 2)}╗{a['reset']}")
    title = board["title"].center(w - 2)
    lines.append(f"{a['bg']}{a['rope']}║{a['reset']}{a['bg']}{a['bold']}{a['chalk']}{title}{a['reset']}{a['bg']}{a['rope']}║{a['reset']}")
    sub = board["subtitle"].center(w - 2)
    lines.append(f"{a['bg']}{a['rope']}║{a['reset']}{a['bg']}{a['dim']}{a['chalk']}{sub}{a['reset']}{a['bg']}{a['rope']}║{a['reset']}")
    date_line = board.get("display_date", "").center(w - 2)
    lines.append(f"{a['bg']}{a['rope']}║{a['reset']}{a['bg']}{a['gold']}{date_line}{a['reset']}{a['bg']}{a['rope']}║{a['reset']}")
    lines.append(f"{a['bg']}{a['rope']}╠{'═' * (w - 2)}╣{a['reset']}")

    for section_key in ("lobster", "oyster", "special"):
        emoji, heading, _u = _SECTION_META[section_key]
        items = board["sections"].get(section_key, [])
        accent = a["lobster"] if section_key == "lobster" else a["ocean"] if section_key == "oyster" else a["gold"]
        head = f" {emoji}  {heading} "
        pad = w - 2 - len(head)
        lines.append(f"{a['bg']}{a['rope']}║{a['reset']}{a['bg']}{accent}{a['bold']}{head}{' ' * max(0, pad)}{a['reset']}{a['bg']}{a['rope']}║{a['reset']}")
        if not items:
            empty = "  (nothing on the board yet)".ljust(w - 2)[: w - 2]
            lines.append(f"{a['bg']}{a['rope']}║{a['reset']}{a['bg']}{a['dim']}{a['chalk']}{empty}{a['reset']}{a['bg']}{a['rope']}║{a['reset']}")
        else:
            for item in items[:12]:
                visible = f"  {item['label']:<18} {item['price_str']:>12}  {item['market_short']}"[: w - 2]
                visible = visible.ljust(w - 2)
                lines.append(
                    f"{a['bg']}{a['rope']}║{a['reset']}{a['bg']}{a['chalk']}{visible}{a['reset']}{a['bg']}{a['rope']}║{a['reset']}"
                )
        sep = f"{a['rope']}{'·' * (w - 2)}{a['reset']}"
        lines.append(f"{a['bg']}{a['rope']}║{a['reset']}{a['bg']}{sep}{a['bg']}{a['rope']}║{a['reset']}")

    demo_note = "  DEMO BOARD — run scrape_markets.py" if board.get("is_demo") else f"  {board['total_items']} items · AAA-gated"
    demo_note = demo_note.center(w - 2)[: w - 2]
    lines.append(f"{a['bg']}{a['rope']}║{a['reset']}{a['bg']}{a['dim']}{a['chalk']}{demo_note}{a['reset']}{a['bg']}{a['rope']}║{a['reset']}")
    lines.append(f"{a['bg']}{a['rope']}╚{'═' * (w - 2)}╝{a['reset']}")
    return "\n".join(lines)


# ---- HTML chalkboard ----

def render_html(board: dict) -> str:
  sections_html = []
  for section_key in ("lobster", "oyster", "special"):
      emoji, heading, _ = _SECTION_META[section_key]
      items = board["sections"].get(section_key, [])
      css_class = f"section-{section_key}"
      rows = []
      for item in items[:20]:
          rows.append(
              f'<div class="item">'
              f'<span class="item-name">{html.escape(item["label"])}</span>'
              f'<span class="item-dots"></span>'
              f'<span class="item-price">{html.escape(item["price_str"])}</span>'
              f'<span class="item-market">{html.escape(item["market_short"])}</span>'
              f'</div>'
          )
      if not rows:
          rows.append('<div class="empty">Check back after the next scrape…</div>')
      sections_html.append(
          f'<section class="board-section {css_class}">'
          f'<h2><span class="emoji">{emoji}</span> {html.escape(heading)}</h2>'
          f'{"".join(rows)}'
          f'</section>'
      )

  demo_banner = (
      '<div class="demo-banner">Demo board — run <code>python3 scripts/scrape_markets.py</code> for live prices</div>'
      if board.get("is_demo") else ""
  )
  updated = html.escape(board.get("updated_at", "")[:19].replace("T", " "))

  return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(board["title"])}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Caveat:wght@500;700&family=Libre+Baskerville:ital@0;1&display=swap" rel="stylesheet">
  <style>
    :root {{
      --slate: #1a2332;
      --slate-light: #243044;
      --chalk: #f4f1ea;
      --chalk-dim: #c9c4b8;
      --lobster: #e85d4c;
      --ocean: #5eb3d6;
      --gold: #e8c547;
      --rope: #8b6914;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      min-height: 100vh;
      background: #0d1117;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 1.5rem;
      font-family: 'Libre Baskerville', Georgia, serif;
    }}
    .board-frame {{
      max-width: 720px;
      width: 100%;
      padding: 12px;
      background: linear-gradient(135deg, #6b4f1d 0%, #8b6914 50%, #5c4612 100%);
      border-radius: 6px;
      box-shadow: 0 20px 60px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.15);
    }}
    .board {{
      background:
        radial-gradient(ellipse at 20% 30%, rgba(255,255,255,0.03) 0%, transparent 50%),
        radial-gradient(ellipse at 80% 70%, rgba(0,0,0,0.15) 0%, transparent 40%),
        linear-gradient(175deg, var(--slate-light) 0%, var(--slate) 40%, #141c28 100%);
      border: 3px solid #2d3a4d;
      border-radius: 4px;
      padding: 2rem 2.25rem 1.75rem;
      color: var(--chalk);
      position: relative;
    }}
    .board::before {{
      content: '';
      position: absolute;
      inset: 0;
      background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.04'/%3E%3C/svg%3E");
      pointer-events: none;
      border-radius: 2px;
    }}
    header {{ text-align: center; margin-bottom: 1.75rem; position: relative; }}
    h1 {{
      font-family: 'Caveat', cursive;
      font-size: 2.75rem;
      font-weight: 700;
      letter-spacing: 0.04em;
      text-shadow: 1px 2px 0 rgba(0,0,0,0.3);
      color: var(--chalk);
    }}
    .subtitle {{ font-size: 0.85rem; color: var(--chalk-dim); font-style: italic; margin-top: 0.25rem; }}
    .date {{ font-family: 'Caveat', cursive; font-size: 1.35rem; color: var(--gold); margin-top: 0.5rem; }}
    .board-section {{ margin-bottom: 1.5rem; position: relative; }}
    .board-section h2 {{
      font-family: 'Caveat', cursive;
      font-size: 1.65rem;
      font-weight: 700;
      margin-bottom: 0.65rem;
      padding-bottom: 0.35rem;
      border-bottom: 2px dashed rgba(244,241,234,0.25);
    }}
    .section-lobster h2 {{ color: var(--lobster); }}
    .section-oyster h2 {{ color: var(--ocean); }}
    .section-special h2 {{ color: var(--gold); }}
    .emoji {{ font-style: normal; }}
    .item {{
      display: grid;
      grid-template-columns: 1fr auto auto;
      gap: 0.5rem 1rem;
      align-items: baseline;
      font-family: 'Caveat', cursive;
      font-size: 1.45rem;
      padding: 0.2rem 0;
    }}
    .item-name {{ color: var(--chalk); }}
    .item-price {{ font-weight: 700; color: var(--chalk); white-space: nowrap; }}
    .section-lobster .item-price {{ color: #ff8a7a; }}
    .section-oyster .item-price {{ color: #8ed4f0; }}
    .section-special .item-price {{ color: var(--gold); }}
    .item-market {{
      grid-column: 1 / -1;
      font-family: 'Libre Baskerville', serif;
      font-size: 0.7rem;
      color: var(--chalk-dim);
      font-style: italic;
      margin-top: -0.15rem;
      padding-left: 0.25rem;
    }}
    .empty {{ font-style: italic; color: var(--chalk-dim); font-size: 0.95rem; }}
    footer {{
      text-align: center;
      margin-top: 1rem;
      padding-top: 1rem;
      border-top: 2px dashed rgba(244,241,234,0.2);
      font-size: 0.75rem;
      color: var(--chalk-dim);
      position: relative;
    }}
    .demo-banner {{
      background: rgba(232, 197, 71, 0.15);
      border: 1px dashed var(--gold);
      color: var(--gold);
      padding: 0.5rem 1rem;
      border-radius: 4px;
      font-size: 0.8rem;
      margin-bottom: 1.25rem;
      text-align: center;
    }}
    code {{ background: rgba(0,0,0,0.3); padding: 0.1em 0.35em; border-radius: 3px; }}
  </style>
</head>
<body>
  <div class="board-frame">
    <div class="board">
      {demo_banner}
      <header>
        <h1>{html.escape(board["title"])}</h1>
        <p class="subtitle">{html.escape(board["subtitle"])}</p>
        <p class="date">{html.escape(board.get("display_date", ""))}</p>
      </header>
      {"".join(sections_html)}
      <footer>
        {board["total_items"]} items · AAA-gated · updated {updated}
      </footer>
    </div>
  </div>
</body>
</html>"""


def write_html_board(path: Path | None = None, **kwargs) -> Path:
    board = get_board(**kwargs)
    out = path or (DATA_DIR / "board.html")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_html(board), encoding="utf-8")
    return out


# ---- Telegram board formatting ----

def render_telegram_board(
    market: str,
    items: list[dict],
    *,
    heading: str = "TODAY'S CATCH",
    emoji: str = "🐟",
) -> str:
    """Chalkboard-style monospace block for Telegram."""
    lines = [f"{emoji} *{heading}* — {market}", "```"]
    lines.append("╔════════════════════════════╗")
    lines.append(f"║  {heading[:24].ljust(24)}  ║")
    lines.append("╠════════════════════════════╣")
    for item in items[:8]:
        label = label_for(item.get("key", item.get("label", "?")))[:14]
        price = item.get("price_str") or format_price(
            float(item.get("price", 0)), item.get("unit", "lb"),
        )
        row = f"  {label:<14} {price:>10}"
        lines.append(f"║{row:<28}║")
    lines.append("╚════════════════════════════╝")
    lines.append("```")
    return "\n".join(lines)
