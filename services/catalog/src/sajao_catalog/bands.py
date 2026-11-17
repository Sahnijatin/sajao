"""Budget bands and product groups.

Bands are per category family, cut at the price terciles of the development listings
(211 listings from two Indian retailers). Re-cut them when feeds widen the catalog.
"""

from __future__ import annotations

from typing import Literal

Band = Literal["value", "mid", "premium"]

# Upper bounds in INR of the value and mid bands; premium is everything above.
CUTS: dict[str, tuple[int, int]] = {
    "sofa": (42_000, 65_000),
    "bed": (15_000, 33_000),
    "table": (11_000, 17_000),
    "chair": (9_000, 24_000),
    "storage": (9_000, 36_000),
    "lighting": (1_800, 4_500),
    "decor": (300, 1_500),
}

# Fine category -> (family for banding, contract product group)
FAMILY: dict[str, tuple[str, str]] = {
    "sofa": ("sofa", "furniture"),
    "bed": ("bed", "furniture"),
    "coffee_table": ("table", "furniture"),
    "side_table": ("table", "furniture"),
    "bedside_table": ("table", "furniture"),
    "armchair": ("chair", "furniture"),
    "accent_chair": ("chair", "furniture"),
    "wardrobe": ("storage", "furniture"),
    "shelf": ("storage", "furniture"),
    "tv_unit": ("storage", "furniture"),
    "floor_lamp": ("lighting", "lighting"),
    "table_lamp": ("lighting", "lighting"),
    "plant": ("decor", "decor"),
}


def family(category: str) -> str:
    return FAMILY[category][0]


def group(category: str) -> str:
    return FAMILY[category][1]


def band(category: str, price_inr: float) -> Band:
    low, high = CUTS[family(category)]
    if price_inr < low:
        return "value"
    if price_inr < high:
        return "mid"
    return "premium"
