"""State helpers — read-or-bootstrap JSONL files (preflight pitfall: never crash on missing file)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"
PARSER_VERSION = "lobster-price-monitor/1.1"


def _ensure_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def ensure_logs_dir() -> Path:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    return LOGS_DIR


def append_jsonl(name: str, row: dict) -> None:
    """Append a single row to a JSONL file. Creates dir + file if missing."""
    _ensure_dir()
    p = DATA_DIR / name
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def price_dedupe_key(row: dict) -> tuple:
    """Stable key for deduplicating gated price rows at persistence time."""
    return (
        row.get("market", ""),
        row.get("post_id", ""),
        row.get("kind", ""),
        row.get("key", ""),
        row.get("unit", ""),
        round(float(row.get("price", 0)), 2),
    )


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


def write_json(name: str, payload: dict) -> Path:
    _ensure_dir()
    p = DATA_DIR / name
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return p


def read_json(name: str) -> dict | None:
    p = DATA_DIR / name
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def persist_key(row: dict) -> str:
    """Stable dedupe key for a gated price row within one scrape run."""
    return "|".join(
        [
            row.get("market", ""),
            row.get("post_id", ""),
            row.get("kind", ""),
            row.get("key", ""),
            f"{float(row.get('price', 0)):.2f}",
            row.get("unit", "lb"),
            row.get("source", ""),
        ]
    )


def _stale_lobster_keys(rows: list[dict]) -> set[tuple]:
    """Legacy lobster keys superseded by shell-qualified keys for the same market."""
    lobster_keys_by_market: dict[str, set[str]] = {}
    for row in rows:
        if row.get("kind") == "lobster_tier":
            lobster_keys_by_market.setdefault(row.get("market", ""), set()).add(row.get("key", ""))

    stale: set[tuple] = set()
    legacy = {
        "hard_shell",
        "soft_shell",
        "chicks",
        "1lb",
        "1.25lb",
        "1.5lb",
        "1.75lb",
        "2lb_plus",
    }
    for row in rows:
        if row.get("kind") != "lobster_tier":
            continue
        key = row.get("key", "")
        market = row.get("market", "")
        if key not in legacy:
            continue
        keys = lobster_keys_by_market.get(market, set())
        qualified = any(k.endswith("_hard_shell") or k.endswith("_soft_shell") for k in keys)
        if qualified:
            stale.add((market, "lobster_tier", key))
    return stale


def compact_prices_jsonl(*, min_confidence: int = 0) -> int:
    """Rewrite prices.jsonl keeping only the latest row per market+kind+key.

    Drops legacy lobster tier keys when shell-qualified replacements exist.
    Returns the number of rows written.
    """
    rows = read_jsonl("prices.jsonl")
    latest: dict[tuple, dict] = {}
    for row in rows:
        if row.get("gate_passed") is False:
            continue
        if row.get("reject_reason"):
            continue
        if int(row.get("confidence", 0)) < min_confidence:
            continue
        identity = (
            row.get("market", ""),
            row.get("kind", ""),
            row.get("key", ""),
        )
        prev = latest.get(identity)
        if prev is None or row.get("observed_at", "") >= prev.get("observed_at", ""):
            latest[identity] = row
    compacted = list(latest.values())
    stale = _stale_lobster_keys(compacted)
    if stale:
        compacted = [
            r
            for r in compacted
            if (r.get("market", ""), r.get("kind", ""), r.get("key", "")) not in stale
        ]
    compacted.sort(
        key=lambda r: (
            r.get("observed_at", ""),
            r.get("market", ""),
            r.get("kind", ""),
            r.get("key", ""),
        ),
    )
    p = DATA_DIR / "prices.jsonl"
    _ensure_dir()
    with p.open("w", encoding="utf-8") as f:
        for row in compacted:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return len(compacted)


def append_jsonl_deduped(
    name: str,
    row: dict,
    *,
    seen: set[str] | None = None,
    key_fn: Callable[[dict], str] | None = None,
) -> bool:
    """Append row if key not already seen this run. Returns True if appended."""
    key = (key_fn or persist_key)(row)
    if seen is not None:
        if key in seen:
            return False
        seen.add(key)
    append_jsonl(name, row)
    return True


def seen_post_ids(name: str, market: str) -> set[str]:
    """Return the set of post_ids already in a JSONL file for a market."""
    return {r["post_id"] for r in read_jsonl(name) if r.get("market") == market}


def build_history_post_index(rows: list[dict] | None = None) -> dict[str, set[str]]:
    """Build market → post_id index from history rows (single read per scrape run)."""
    if rows is None:
        rows = read_jsonl("history.jsonl")
    index: dict[str, set[str]] = {}
    for row in rows:
        market = row.get("market", "")
        post_id = row.get("post_id")
        if market and post_id:
            index.setdefault(market, set()).add(str(post_id))
    return index


def count_passed_rows_by_market(rows: list[dict] | None = None) -> dict[str, int]:
    """Count gate-passed price rows per market."""
    if rows is None:
        rows = read_jsonl("prices.jsonl")
    counts: dict[str, int] = {}
    for row in rows:
        if row.get("gate_passed", True):
            market = row.get("market", "")
            counts[market] = counts.get(market, 0) + 1
    return counts


def recent_history_posts(
    market: str,
    *,
    max_age_days: int = 7,
    limit: int = 5,
) -> list[dict]:
    """Return newest history posts for a market within max_age_days (FB fallback)."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    rows = [
        r
        for r in read_jsonl("history.jsonl")
        if r.get("market") == market
        and r.get("source") in ("facebook", "facebook_search", "reference")
        and r.get("post_id")
        and r.get("text")
    ]
    fresh: list[tuple[datetime, dict]] = []
    for row in rows:
        ts = row.get("timestamp", "")
        if not ts:
            continue
        s = ts.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(s)
        except ValueError:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if dt.astimezone(timezone.utc) >= cutoff:
            fresh.append((dt, row))
    fresh.sort(key=lambda x: x[0], reverse=True)
    seen: set[str] = set()
    out: list[dict] = []
    for _, row in fresh:
        pid = str(row["post_id"])
        if pid in seen:
            continue
        seen.add(pid)
        out.append(row)
        if len(out) >= limit:
            break
    return out


def seen_alert_keys() -> set[str]:
    """Return alert dedupe keys (market|tier|price or market|post_id|special)."""
    return {r["key"] for r in read_jsonl("alerts_sent.jsonl") if r.get("key")}


def data_path(name: str) -> Path:
    return DATA_DIR / name


def latest_run_log() -> dict | None:
    rows = read_jsonl("run-log.jsonl")
    return rows[-1] if rows else None


def last_web_specials(market: str) -> set[tuple[str, float, str]]:
    """Return set of (key, price, unit) special rows from the most recent web snapshot."""
    rows = read_jsonl("web-snapshots.jsonl")
    market_rows = [r for r in rows if r.get("market") == market]
    if not market_rows:
        return set()
    latest = market_rows[-1]
    return {(s["key"], float(s["price"]), s["unit"]) for s in latest.get("specials", [])}


def save_web_snapshot(market: str, specials: list[dict]) -> None:
    """Persist current web catalog special rows for diff alerting."""
    append_jsonl(
        "web-snapshots.jsonl",
        {
            "market": market,
            "ts": datetime.now(timezone.utc).isoformat(),
            "specials": specials,
        },
    )


def rotate_state_files(max_days: int = 90) -> None:
    """Rotate jsonl state files, dropping rows older than max_days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_days)

    # Files and their corresponding timestamp fields
    targets = [
        ("history.jsonl", ["timestamp", "observed_at"]),
        ("run-log.jsonl", ["ts"]),
        ("quarantine.jsonl", ["observed_at"]),
        ("alerts_sent.jsonl", ["observed_at", "ts"]),
        ("web-snapshots.jsonl", ["ts"]),
    ]

    for filename, fields in targets:
        p = DATA_DIR / filename
        if not p.exists():
            continue
        rows = read_jsonl(filename)
        kept: list[dict] = []
        for r in rows:
            ts_str = None
            for f in fields:
                if r.get(f):
                    ts_str = r[f]
                    break
            if not ts_str:
                kept.append(r)
                continue

            s = ts_str.replace("Z", "+00:00")
            try:
                dt = datetime.fromisoformat(s)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                if dt.astimezone(timezone.utc) >= cutoff:
                    kept.append(r)
            except ValueError:
                kept.append(r)

        _ensure_dir()
        with p.open("w", encoding="utf-8") as f_out:
            for r in kept:
                f_out.write(json.dumps(r, ensure_ascii=False) + "\n")
