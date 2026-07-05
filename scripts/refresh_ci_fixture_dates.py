#!/usr/bin/env python3
"""Shift CI B+ fixture timestamps so the newest row is current (within 24h freshness)."""

from __future__ import annotations

import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "fixtures" / "ci_gate_bplus"
DST = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data"

ISO_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)
DATE_FIELDS = frozenset(
    {
        "observed_at",
        "timestamp",
        "ts",
        "fetch_timestamp",
        "updated_at",
    }
)


def _parse_iso(value: str) -> datetime | None:
    if not isinstance(value, str) or not ISO_RE.match(value):
        return None
    s = value.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _format_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _collect_max_ts(obj: object, current: datetime | None) -> datetime | None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in DATE_FIELDS:
                parsed = _parse_iso(v) if isinstance(v, str) else None
                if parsed and (current is None or parsed > current):
                    current = parsed
            current = _collect_max_ts(v, current)
    elif isinstance(obj, list):
        for item in obj:
            current = _collect_max_ts(item, current)
    return current


def _shift_dates(obj: object, delta_seconds: float) -> object:
    from datetime import timedelta

    if isinstance(obj, dict):
        out: dict = {}
        for k, v in obj.items():
            if k in DATE_FIELDS and isinstance(v, str):
                parsed = _parse_iso(v)
                if parsed:
                    out[k] = _format_iso(parsed + timedelta(seconds=delta_seconds))
                    continue
            out[k] = _shift_dates(v, delta_seconds)
        return out
    if isinstance(obj, list):
        return [_shift_dates(item, delta_seconds) for item in obj]
    return obj


def _load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )


def refresh_bplus_fixtures(*, src: Path = SRC, dst: Path = DST) -> None:
    if not src.is_dir():
        raise FileNotFoundError(f"B+ fixture source missing: {src}")

    dst.mkdir(parents=True, exist_ok=True)

    payloads: dict[str, object] = {}
    for name in ("prices.jsonl", "history.jsonl", "run-log.jsonl", "market-coverage.json"):
        path = src / name
        if not path.exists():
            raise FileNotFoundError(f"Missing fixture: {path}")
        if name.endswith(".jsonl"):
            payloads[name] = _load_jsonl(path)
        else:
            payloads[name] = json.loads(path.read_text(encoding="utf-8"))

    max_ts = _collect_max_ts(list(payloads.values()), None)
    if max_ts is None:
        raise ValueError("No parseable timestamps in B+ fixtures")

    now = datetime.now(timezone.utc)
    delta = (now - max_ts).total_seconds()
    shifted = {name: _shift_dates(data, delta) for name, data in payloads.items()}

    _write_jsonl(dst / "prices.jsonl", shifted["prices.jsonl"])  # type: ignore[arg-type]
    _write_jsonl(dst / "history.jsonl", shifted["history.jsonl"])  # type: ignore[arg-type]
    run_rows = shifted["run-log.jsonl"]  # type: ignore[assignment]
    if isinstance(run_rows, list) and run_rows:
        _write_jsonl(dst / "run-log.jsonl", run_rows)
    (dst / "market-coverage.json").write_text(
        json.dumps(shifted["market-coverage.json"], indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    # Copy any other static files if added later
    for extra in src.iterdir():
        if extra.name in payloads or extra.name.startswith("."):
            continue
        if extra.is_file():
            shutil.copy2(extra, dst / extra.name)


def main() -> int:
    try:
        refresh_bplus_fixtures()
    except (FileNotFoundError, ValueError) as e:
        print(f"refresh_ci_fixture_dates: {e}", file=sys.stderr)
        return 1
    print(f"Refreshed B+ fixtures into {DST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
