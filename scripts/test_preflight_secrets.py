"""Tests for scripts/preflight_secrets.sh."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "preflight_secrets.sh"


def _run(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        env=merged,
    )


def test_preflight_dry_run_exits_zero() -> None:
    proc = _run("--dry-run")
    assert proc.returncode == 0, proc.stderr
    assert "Secrets preflight OK" in proc.stdout
    assert "[dry-run]" in proc.stdout


def test_preflight_require_telegram_fails_without_token() -> None:
    with tempfile.TemporaryDirectory() as td:
        secrets = Path(td) / ".openclaw" / "secrets"
        secrets.mkdir(parents=True)
        proc = _run(
            "--require-telegram",
            env={"HOME": td},
        )
    assert proc.returncode == 1, proc.stdout
    combined = proc.stdout + proc.stderr
    assert "herb.token" in combined or "Telegram bot token" in combined


def test_preflight_require_telegram_passes_with_token() -> None:
    with tempfile.TemporaryDirectory() as td:
        tg = Path(td) / ".openclaw" / "secrets" / "telegram"
        tg.mkdir(parents=True)
        (tg / "herb.token").write_text("fake-token\n", encoding="utf-8")
        proc = _run(
            "--require-telegram",
            env={"HOME": td, "LOBSTER_TELEGRAM_CHAT_ID": "12345"},
        )
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    assert "Secrets preflight OK" in proc.stdout


def main() -> int:
    tests = [
        test_preflight_dry_run_exits_zero,
        test_preflight_require_telegram_fails_without_token,
        test_preflight_require_telegram_passes_with_token,
    ]
    failed = 0
    for test in tests:
        name = test.__name__
        try:
            test()
            print(f"  ✓ {name}")
        except Exception as e:
            print(f"  ✗ {name}: {e}")
            failed += 1

    if failed:
        print(f"\n{failed} test(s) failed")
        return 1
    print("\nAll preflight_secrets tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
