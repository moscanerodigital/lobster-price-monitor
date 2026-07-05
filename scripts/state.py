"""State helpers — read-or-bootstrap JSONL files (preflight pitfall: never crash on missing file)."""
from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Iterable, Iterator

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _ensure_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def append_jsonl(name: str, row: dict) -> None:
    """Append a single row to a JSONL file. Creates dir + file if missing."""
    _ensure_dir()
    p = DATA_DIR / name
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_jsonl(name: str) -> list[dict]:
    """Read all rows from a JSONL file. Returns [] if missing/empty."""
    p = DATA_DIR / name
    if not p.exists() or p.stat().st_size == 0:
        return []
    rows: list[dict] = []
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def seen_post_ids(name: str, market: str) -> set[str]:
    """Return the set of (market, post_id) pairs already in a JSONL file (read-or-bootstrap)."""
    return {r["post_id"] for r in read_jsonl(name) if r.get("market") == market}


def seen_alert_keys() -> set[str]:
    """Return alert dedupe keys (market|tier|price or market|post_id|special)."""
    return {r["key"] for r in read_jsonl("alerts_sent.jsonl") if r.get("key")}


def data_path(name: str) -> Path:
    return DATA_DIR / name


def last_web_specials(market: str) -> set[tuple[str, float, str]]:
    """Return set of (key, price, unit) special rows from the most recent web snapshot."""
    rows = read_jsonl("web-snapshots.jsonl")
    market_rows = [r for r in rows if r.get("market") == market]
    if not market_rows:
        return set()
    latest = market_rows[-1]
    return {
        (s["key"], float(s["price"]), s["unit"])
        for s in latest.get("specials", [])
    }


def save_web_snapshot(market: str, specials: list[dict]) -> None:
    """Persist current web catalog special rows for diff alerting."""
    append_jsonl("web-snapshots.jsonl", {
        "market": market,
        "ts": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "specials": specials,
    })
