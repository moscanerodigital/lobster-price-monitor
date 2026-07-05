"""Configured seafood markets for scrape and board display."""

from __future__ import annotations

MARKETS: list[dict] = [
    {
        "name": "Ancient Mariner Lobster Co.",
        "location": "Westbrook",
        "fb_handle": "amlobsterco",
        "web": None,
    },
    {
        "name": "Two Tides Seafood",
        "location": "Scarborough",
        "fb_handle": "100054888565201",
        "web": None,
    },
    {
        "name": "Scarborough Fish & Lobster",
        "location": "Scarborough",
        "fb_handle": "CheapMaineLobster",
        "web": None,
    },
    {
        "name": "Pine Tree Seafood & Produce",
        "location": "Scarborough",
        "fb_handle": "PineTreeSeafood",
        "web": "https://pinetreeseafood.com/shop",
    },
    {
        "name": "Harbor Fish Market (Lobster)",
        "location": "Portland + Scarborough",
        "fb_handle": "harborfishmarket",
        "web": "https://harborfish.com/product-category/all/lobster/live-lobster/",
        "web_extra": [
            "https://harborfish.com/product-category/all/fish/",
        ],
    },
    {
        "name": "Harbor Fish Market (Oysters)",
        "location": "Portland + Scarborough",
        "fb_handle": "harborfishmarket",
        "web": "https://harborfish.com/product-category/all/shellfish/oysters/",
    },
    {
        "name": "Free Range Fish & Lobster",
        "location": "Portland",
        "fb_handle": "freerangefishandlobster",
        "web": None,
    },
    {
        "name": "SoPo Seafood Market & Raw Bar",
        "location": "South Portland",
        "fb_handle": "soposeafood",
        "web": None,
    },
    {
        "name": "Five Islands Lobster Co.",
        "location": "Georgetown",
        "fb_handle": "fiveislandslobsterco",
        "web": None,
        "reference_url": "https://fiveislandslobster.com/menu/",
    },
]
