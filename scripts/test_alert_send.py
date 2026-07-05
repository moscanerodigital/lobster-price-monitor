#!/usr/bin/env python3
"""Test Telegram alert formatting and sending. Bypasses normal dry-run suppression."""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from send_alert import alert_lobster_drop, alert_specials_post, SECRETS


def main() -> int:
    print("=== Telegram Alert Test ===")
    if not SECRETS.exists():
        print(f"ERROR: Telegram token file is missing at {SECRETS}", file=sys.stderr)
        print("Please place Erik's bot token in this file to test alerts.", file=sys.stderr)
        return 1

    print("Token file found.")
    
    # Send a lobster drop alert
    market = "Ancient Mariner Lobster Co."
    tier = "soft_shell"
    price = 6.99
    url = "https://www.facebook.com/amlobsterco/posts/test_lobster_drop"
    ts = "2026-07-05T03:00:00+00:00"
    
    print(f"Sending test lobster drop alert for {market} soft_shell at ${price:.2f}/lb...")
    # Add a timestamp suffix to ensure key uniqueness during testing
    import time
    test_tier = f"{tier}_test_{int(time.time())}"
    ok1 = alert_lobster_drop(
        market=market,
        tier=test_tier,
        price=price,
        post_url=url,
        observed_at=ts,
        threshold=8.00,
        confidence=95,
    )
    
    if ok1:
        print("  ✓ Lobster drop alert sent successfully.")
    else:
        print("  ✗ Lobster drop alert failed (or was deduped).", file=sys.stderr)

    # Send a specials post alert
    specials = [
        {"key": "halibut", "price": 17.99, "unit": "lb", "confidence": 85},
        {"key": "lobster_roll", "price": 21.00, "unit": "ea", "confidence": 90},
    ]
    test_post_id = f"test_specials_{int(time.time())}"
    url_specials = f"https://www.facebook.com/amlobsterco/posts/{test_post_id}"
    
    print(f"Sending test specials post alert for {market}...")
    ok2 = alert_specials_post(
        market=market,
        post_url=url_specials,
        snippet="Fresh halibut $17.99/lb and lobster rolls $21.00 each today!",
        observed_at=ts,
        special_items=specials,
        source="facebook",
    )
    
    if ok2:
        print("  ✓ Specials post alert sent successfully.")
    else:
        print("  ✗ Specials post alert failed (or was deduped).", file=sys.stderr)

    if ok1 and ok2:
        print("All test alerts sent successfully.")
        return 0
    else:
        print("Some alerts failed to send. Check bot configuration, chat ID, or internet connection.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
