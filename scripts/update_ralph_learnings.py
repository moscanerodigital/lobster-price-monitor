#!/usr/bin/env python3
"""Auto-populate RALPH.md Learnings section from run-log data."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from board_render import human_blocker_reason
from state import read_jsonl

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RALPH = ROOT / "RALPH.md"
LEARNINGS_HEADER = "## Learnings"
USAGE_HEADER = "## Usage / Budget Log"
AUTO_HEADER = "<!-- auto-updated from run-log -->"
PLACEHOLDER = "(empty — populated by each run)"


def _blocked_markets(run: dict) -> list[str]:
    lines: list[str] = []
    for entry in run.get("market_coverage") or []:
        status = entry.get("status", "")
        if status in ("blocked", "partial"):
            name = entry.get("market") or entry.get("name") or "?"
            blocker = entry.get("blocker") or ""
            reason = human_blocker_reason(str(blocker)) if blocker else status
            lines.append(f"- **{name}** ({status}): {reason}")
    if not lines:
        for err in run.get("errors") or []:
            blocker = err.get("blocker")
            if blocker:
                name = err.get("market", "?")
                reason = human_blocker_reason(str(blocker))
                lines.append(f"- **{name}** (blocked): {reason}")
    return lines


def _run_summary(run: dict) -> str:
    ts = run.get("ts", "?")
    succeeded = run.get("markets_succeeded", 0)
    attempted = run.get("markets_attempted", 0)
    duration = run.get("duration_seconds")
    duration_str = f"{duration:.1f}s" if duration is not None else "?"
    avg_conf = run.get("avg_confidence", 0)
    alerts_on = run.get("alerts_enabled", False)
    lobster = run.get("lobster_alerts", 0)
    oyster = run.get("oyster_alerts", 0)
    special = run.get("special_alerts", 0)
    suppressed = run.get("alerts_suppressed", 0)
    alert_bits = [
        f"{lobster} lobster",
        f"{oyster} oyster",
        f"{special} specials",
    ]
    alert_line = ", ".join(alert_bits)
    if not alerts_on and suppressed:
        alert_line += f"; {suppressed} suppressed (--no-alerts)"
    return (
        f"- **Latest run** ({ts}): {succeeded}/{attempted} markets, "
        f"{duration_str}, avg conf {avg_conf:.1f}; alerts: {alert_line}"
    )


def build_learnings_body(*, max_runs: int = 3) -> str:
    runs = read_jsonl("run-log.jsonl")
    if not runs:
        return f"{AUTO_HEADER}\n\n(no run-log entries yet)\n"

    recent = runs[-max_runs:]
    lines: list[str] = [AUTO_HEADER, ""]

    for i, run in enumerate(reversed(recent)):
        if i == 0:
            lines.append(_run_summary(run))
        else:
            ts = run.get("ts", "?")
            succeeded = run.get("markets_succeeded", 0)
            attempted = run.get("markets_attempted", 0)
            lines.append(f"- **Prior run** ({ts}): {succeeded}/{attempted} markets")

        blocked = _blocked_markets(run)
        if blocked and i == 0:
            lines.extend(blocked[:5])

    lines.append("")
    return "\n".join(lines)


def _replace_learnings_section(ralph_text: str, body: str) -> str:
    pattern = re.compile(
        rf"({re.escape(LEARNINGS_HEADER)}\n\n)(.*?)(\n{re.escape(USAGE_HEADER)})",
        re.DOTALL,
    )
    match = pattern.search(ralph_text)
    if not match:
        raise ValueError(f"Could not find {LEARNINGS_HEADER} section in RALPH.md")
    return ralph_text[: match.start(2)] + body.rstrip() + "\n\n" + ralph_text[match.start(3) + 1 :]


def update_learnings(*, ralph_path: Path = DEFAULT_RALPH, dry_run: bool = False) -> str:
    body = build_learnings_body()
    if dry_run:
        return body

    text = ralph_path.read_text(encoding="utf-8")
    updated = _replace_learnings_section(text, body)
    ralph_path.write_text(updated, encoding="utf-8")
    return body


def learnings_populated(text: str) -> bool:
    """True when Learnings section has real content (not placeholder)."""
    pattern = re.compile(
        rf"{re.escape(LEARNINGS_HEADER)}\n\n(.*?)\n{re.escape(USAGE_HEADER)}",
        re.DOTALL,
    )
    match = pattern.search(text)
    if not match:
        return False
    content = match.group(1).strip()
    if not content:
        return False
    if PLACEHOLDER in content:
        return False
    if content == AUTO_HEADER:
        return False
    if content == "(no run-log entries yet)":
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Update RALPH.md Learnings from run-log")
    parser.add_argument("--dry-run", action="store_true", help="Print body without writing")
    parser.add_argument(
        "--ralph-path",
        type=Path,
        default=DEFAULT_RALPH,
        help="Path to RALPH.md",
    )
    args = parser.parse_args()

    try:
        body = update_learnings(ralph_path=args.ralph_path, dry_run=args.dry_run)
    except ValueError as e:
        print(f"update_ralph_learnings: {e}", file=sys.stderr)
        return 1

    if args.dry_run:
        print(body)
    else:
        print(f"Updated learnings in {args.ralph_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
