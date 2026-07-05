"""Canonical short display names for markets."""

from __future__ import annotations

MARKET_SHORTCUTS = {
    "Ancient Mariner Lobster Co.": "Ancient Mariner",
    "Pine Tree Seafood & Produce": "Pine Tree",
    "Harbor Fish Market (Lobster)": "Harbor Fish",
    "Harbor Fish Market (Oysters)": "Harbor Fish Oys",
    "Scarborough Fish & Lobster": "Scarborough F&L",
    "Free Range Fish & Lobster": "Free Range",
    "SoPo Seafood Market & Raw Bar": "SoPo Seafood",
    "Two Tides Seafood": "Two Tides",
    "Five Islands Lobster Co.": "Five Islands",
}


def short_market(name: str) -> str:
    return MARKET_SHORTCUTS.get(name, name.split("(")[0].strip()[:22])
