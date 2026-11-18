"""What each product category needs from the room.

A product's ``category`` decides how it sits in the space (on the floor, as a
rug under other things, on a wall, on the ceiling, or on top of another item),
which of its sides must be reachable, and how much floor in front of it must
stay clear for doors and drawers to open. Unknown categories are treated as
plain floor furniture with no access needs, which is the strict side for
collisions and the lenient side for nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Mount = Literal["floor", "rug", "wall", "ceiling", "surface"]
AccessSide = Literal["front", "left", "right"]


@dataclass(frozen=True)
class Category:
    key: str
    mount: Mount
    # Sides a person must reach. For a bed either long side is enough (see any_side).
    access: tuple[AccessSide, ...] = ()
    any_side: bool = False
    # Floor depth in front that must stay clear so doors and drawers open.
    opening_clearance_m: float = 0.0
    seating: bool = False
    # The back goes against a wall in every archetype.
    wall_backed: bool = False


_CATEGORIES = [
    # Seating
    Category("sofa", "floor", ("front",), seating=True),
    Category("sectional_sofa", "floor", ("front",), seating=True),
    Category("loveseat", "floor", ("front",), seating=True),
    Category("armchair", "floor", ("front",), seating=True),
    Category("accent_chair", "floor", ("front",), seating=True),
    Category("diwan", "floor", ("front",), seating=True),
    Category("bench", "floor", ("front",), seating=True),
    Category("pouf", "floor"),
    Category("ottoman", "floor"),
    Category("desk_chair", "floor"),
    # Tables
    Category("coffee_table", "floor"),
    Category("side_table", "floor"),
    Category("console_table", "floor", ("front",), wall_backed=True),
    Category("study_desk", "floor", ("front",), wall_backed=True),
    Category("nightstand", "floor", opening_clearance_m=0.35),
    # Storage
    Category("tv_unit", "floor", ("front",), opening_clearance_m=0.40, wall_backed=True),
    Category("sideboard", "floor", ("front",), opening_clearance_m=0.45, wall_backed=True),
    Category("bookshelf", "floor", ("front",), opening_clearance_m=0.30, wall_backed=True),
    Category("wardrobe", "floor", ("front",), opening_clearance_m=0.60, wall_backed=True),
    Category("dresser", "floor", ("front",), opening_clearance_m=0.50, wall_backed=True),
    Category("chest_of_drawers", "floor", ("front",), opening_clearance_m=0.50, wall_backed=True),
    Category("shoe_rack", "floor", ("front",), opening_clearance_m=0.35, wall_backed=True),
    # Beds
    Category("bed", "floor", ("left", "right"), any_side=True, wall_backed=True),
    # Lighting
    Category("floor_lamp", "floor"),
    Category("table_lamp", "surface"),
    Category("pendant_light", "ceiling"),
    Category("ceiling_light", "ceiling"),
    Category("wall_light", "wall"),
    # Soft furnishing and decor
    Category("rug", "rug"),
    Category("curtains", "wall"),
    Category("art", "wall"),
    Category("mirror", "wall"),
    Category("wall_shelf", "wall"),
    Category("clock", "wall"),
    Category("floor_mirror", "floor"),
    Category("plant", "floor"),
    Category("cushion", "surface"),
    Category("throw", "surface"),
    Category("vase", "surface"),
    Category("decor", "surface"),
]

CATEGORIES: dict[str, Category] = {c.key: c for c in _CATEGORIES}

# Names the scan uses for things already in the room.
ALIASES = {
    "almirah": "wardrobe",
    "cupboard": "wardrobe",
    "tv_stand": "tv_unit",
    "double_bed": "bed",
    "single_bed": "bed",
    "couch": "sofa",
    "chair": "accent_chair",
    "settee": "loveseat",
    "table": "side_table",
    "carpet": "rug",
    "dressing_table": "dresser",
}


def category(key: str) -> Category:
    key = ALIASES.get(key, key)
    return CATEGORIES.get(key, Category(key, "floor"))
