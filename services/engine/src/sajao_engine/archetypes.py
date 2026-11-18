"""Layout archetypes for living rooms and bedrooms.

An archetype is data: an ordered list of slots, each with the product
categories it takes, whether it is required, and a placement rule relative to
the room or to an earlier slot. The designer picks a product for each slot from
the shortlist; the solver turns the rules into positions. Nothing here sets a
size, a price or a coordinate.

They cover the repeated layouts of Indian flats: a sofa facing a TV wall in a
rectangular hall, a conversation set, an L-sofa in a corner, a sofa on the
short wall of a long hall, a diwan lounge; a bed centered on the headboard wall
with nightstands, a bed in the corner of a small room, a study corner, a
dresser or wardrobe opposite the bed. They grow from real failures.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

SpaceKind = Literal["living_room", "bedroom"]


@dataclass(frozen=True)
class WallPick:
    """Which walls a wall-backed slot may use, and which it prefers."""

    # any; window: has a window; no_window; opposite: faces the target's wall;
    # beside: perpendicular to the target's wall; other: not the target's wall.
    only: Literal["any", "window", "no_window", "opposite", "beside", "other"] = "any"
    target: str | None = None
    prefer: Literal["long", "short", "none"] = "none"


@dataclass(frozen=True)
class AgainstWall:
    walls: WallPick = field(default_factory=WallPick)
    # Prefer the middle of the free stretch of wall (beds, sofas) over a corner.
    centered: bool = True


@dataclass(frozen=True)
class InCorner:
    """Back to one wall and one side to another, in a corner of the floor."""

    walls: WallPick = field(default_factory=WallPick)


@dataclass(frozen=True)
class InFront:
    """In front of the target, centered on it, facing the same way (a coffee table)."""

    target: str
    gap_m: tuple[float, float] = (0.40, 0.50)


@dataclass(frozen=True)
class Facing:
    """Across from the target's front, turned to face it (a chair facing a sofa)."""

    target: str
    distance_m: tuple[float, float] = (1.8, 3.0)


@dataclass(frozen=True)
class AtSide:
    """At the side of the target group, turned toward its middle (a chair beside a coffee table)."""

    target: str
    side: Literal["left", "right", "either"] = "either"
    gap_m: tuple[float, float] = (0.30, 0.60)


@dataclass(frozen=True)
class Beside:
    """Next to the target, backs in line (a side table by a sofa, a nightstand by a bed)."""

    target: str
    side: Literal["left", "right", "either"] = "either"
    gap_m: tuple[float, float] = (0.02, 0.10)


@dataclass(frozen=True)
class Corner:
    """A free floor corner, nearest the target if given (a plant, a floor lamp)."""

    near: str | None = None


@dataclass(frozen=True)
class Under:
    """A rug under the target group: under the front legs of the seating or the lower bed."""

    target: str
    tuck_m: float = 0.15


@dataclass(frozen=True)
class OnWallAbove:
    """A wall item on the wall behind the target, centered on it (art above a sofa or bed)."""

    target: str


@dataclass(frozen=True)
class Ceiling:
    """A ceiling light over the target, or the middle of the room."""

    target: str | None = None


@dataclass(frozen=True)
class OnTop:
    """On top of the target (a table lamp on a nightstand)."""

    target: str


Rule = (
    AgainstWall
    | InCorner
    | InFront
    | Facing
    | AtSide
    | Beside
    | Corner
    | Under
    | OnWallAbove
    | Ceiling
    | OnTop
)


@dataclass(frozen=True)
class Slot:
    key: str
    categories: tuple[str, ...]
    rule: Rule
    required: bool = False


@dataclass(frozen=True)
class Archetype:
    key: str
    space: SpaceKind
    title: str
    slots: tuple[Slot, ...]
    # The smallest floor this archetype makes sense in, in square metres.
    min_area_m2: float = 0.0

    def slot(self, key: str) -> Slot:
        return next(s for s in self.slots if s.key == key)


SOFAS = ("sofa", "loveseat")
CHAIRS = ("armchair", "accent_chair")
DECOR_LIVING = (
    Slot("plant", ("plant",), Corner()),
    Slot("ceiling_light", ("pendant_light", "ceiling_light"), Ceiling()),
)


def _living_tail(seat: str) -> tuple[Slot, ...]:
    return (
        Slot("coffee_table", ("coffee_table",), InFront(seat), required=True),
        Slot("rug", ("rug",), Under(seat)),
        Slot("side_table", ("side_table",), Beside(seat)),
        Slot("floor_lamp", ("floor_lamp",), Corner(near=seat)),
        Slot("art", ("art", "mirror"), OnWallAbove(seat)),
    )


LIVING = (
    Archetype(
        "lr_sofa_tv",
        "living_room",
        "Sofa facing the TV wall",
        (
            Slot("sofa", SOFAS, AgainstWall(WallPick("no_window", prefer="long")), required=True),
            Slot("tv_unit", ("tv_unit",), AgainstWall(WallPick("opposite", "sofa")), required=True),
            *_living_tail("sofa"),
            Slot("armchair", CHAIRS, AtSide("coffee_table")),
            *DECOR_LIVING,
        ),
        min_area_m2=9.0,
    ),
    Archetype(
        "lr_conversation",
        "living_room",
        "Sofa and two chairs around a coffee table",
        (
            Slot("sofa", SOFAS, AgainstWall(WallPick("any", prefer="long")), required=True),
            Slot("coffee_table", ("coffee_table",), InFront("sofa"), required=True),
            Slot("armchair_left", CHAIRS, AtSide("coffee_table", "left"), required=True),
            Slot("armchair_right", CHAIRS, AtSide("coffee_table", "right"), required=True),
            Slot("rug", ("rug",), Under("sofa")),
            Slot("side_table", ("side_table",), Beside("sofa")),
            Slot("tv_unit", ("tv_unit", "sideboard"), AgainstWall(WallPick("opposite", "sofa"))),
            Slot("floor_lamp", ("floor_lamp",), Corner(near="sofa")),
            Slot("art", ("art", "mirror"), OnWallAbove("sofa")),
            *DECOR_LIVING,
        ),
        min_area_m2=12.0,
    ),
    Archetype(
        "lr_corner_sectional",
        "living_room",
        "L-sofa in the corner facing the TV",
        (
            Slot(
                "sofa",
                ("sectional_sofa",),
                InCorner(WallPick("no_window", prefer="long")),
                required=True,
            ),
            Slot("tv_unit", ("tv_unit",), AgainstWall(WallPick("opposite", "sofa")), required=True),
            Slot("coffee_table", ("coffee_table",), InFront("sofa", (0.40, 0.60)), required=True),
            Slot("rug", ("rug",), Under("sofa")),
            Slot("floor_lamp", ("floor_lamp",), Corner(near="sofa")),
            Slot("art", ("art", "mirror"), OnWallAbove("sofa")),
            *DECOR_LIVING,
        ),
        min_area_m2=12.0,
    ),
    Archetype(
        "lr_short_wall",
        "living_room",
        "Sofa on the short wall of a long hall",
        (
            Slot("sofa", SOFAS, AgainstWall(WallPick("any", prefer="short")), required=True),
            Slot("tv_unit", ("tv_unit",), AgainstWall(WallPick("opposite", "sofa"))),
            *_living_tail("sofa"),
            Slot(
                "sideboard",
                ("sideboard", "bookshelf"),
                AgainstWall(WallPick("beside", "sofa"), centered=False),
            ),
            *DECOR_LIVING,
        ),
        min_area_m2=10.0,
    ),
    Archetype(
        "lr_window_sofa",
        "living_room",
        "Low sofa under the window, TV opposite",
        (
            Slot("sofa", SOFAS, AgainstWall(WallPick("window", prefer="long")), required=True),
            Slot("tv_unit", ("tv_unit",), AgainstWall(WallPick("opposite", "sofa")), required=True),
            *_living_tail("sofa"),
            Slot("armchair", CHAIRS, AtSide("coffee_table")),
            *DECOR_LIVING,
        ),
        min_area_m2=9.0,
    ),
    Archetype(
        "lr_diwan_lounge",
        "living_room",
        "Diwan lounge with two chairs, no TV",
        (
            Slot(
                "diwan",
                ("diwan", "sofa"),
                AgainstWall(WallPick("any", prefer="long")),
                required=True,
            ),
            Slot("coffee_table", ("coffee_table",), InFront("diwan", (0.40, 0.55)), required=True),
            Slot("armchair", CHAIRS, Facing("diwan", (1.6, 2.6)), required=True),
            Slot("pouf", ("pouf", "ottoman"), AtSide("coffee_table")),
            Slot("rug", ("rug",), Under("diwan")),
            Slot("side_table", ("side_table",), Beside("diwan")),
            Slot(
                "bookshelf",
                ("bookshelf", "sideboard"),
                AgainstWall(WallPick("other", "diwan"), centered=False),
            ),
            Slot("art", ("art", "mirror"), OnWallAbove("diwan")),
            *DECOR_LIVING,
        ),
        min_area_m2=9.0,
    ),
    Archetype(
        "lr_compact",
        "living_room",
        "Compact hall: loveseat, one chair, TV",
        (
            Slot(
                "sofa",
                ("loveseat", "sofa"),
                AgainstWall(WallPick("no_window", prefer="long")),
                required=True,
            ),
            Slot("tv_unit", ("tv_unit",), AgainstWall(WallPick("opposite", "sofa")), required=True),
            Slot("coffee_table", ("coffee_table", "side_table"), InFront("sofa"), required=True),
            Slot("armchair", CHAIRS, AtSide("coffee_table")),
            Slot("rug", ("rug",), Under("sofa")),
            Slot("plant", ("plant",), Corner()),
            Slot("art", ("art", "mirror"), OnWallAbove("sofa")),
            Slot("ceiling_light", ("pendant_light", "ceiling_light"), Ceiling()),
        ),
    ),
    Archetype(
        "lr_reading_wall",
        "living_room",
        "Sofa and TV with a book wall and reading chair",
        (
            Slot("sofa", SOFAS, AgainstWall(WallPick("no_window", prefer="long")), required=True),
            Slot("tv_unit", ("tv_unit",), AgainstWall(WallPick("opposite", "sofa")), required=True),
            Slot("coffee_table", ("coffee_table",), InFront("sofa"), required=True),
            Slot(
                "bookshelf",
                ("bookshelf",),
                AgainstWall(WallPick("beside", "sofa"), centered=False),
                required=True,
            ),
            Slot("armchair", CHAIRS, Corner(near="bookshelf")),
            Slot("floor_lamp", ("floor_lamp",), Corner(near="armchair")),
            Slot("rug", ("rug",), Under("sofa")),
            Slot("plant", ("plant",), Corner()),
            Slot("ceiling_light", ("pendant_light", "ceiling_light"), Ceiling()),
        ),
        min_area_m2=12.0,
    ),
)


def _bed_tail() -> tuple[Slot, ...]:
    return (
        Slot("rug", ("rug",), Under("bed", tuck_m=1.2)),
        Slot("art", ("art", "mirror"), OnWallAbove("bed")),
        Slot("table_lamp", ("table_lamp",), OnTop("nightstand_left")),
        Slot("ceiling_light", ("pendant_light", "ceiling_light"), Ceiling("bed")),
        Slot("plant", ("plant",), Corner()),
    )


BED_WALL = WallPick("no_window", prefer="long")

BEDROOM = (
    Archetype(
        "br_bed_centered",
        "bedroom",
        "Bed centered on the headboard wall, wardrobe to one side",
        (
            Slot("bed", ("bed",), AgainstWall(BED_WALL), required=True),
            Slot("nightstand_left", ("nightstand",), Beside("bed", "left")),
            Slot("nightstand_right", ("nightstand",), Beside("bed", "right")),
            Slot("wardrobe", ("wardrobe",), AgainstWall(WallPick("other", "bed"), centered=False)),
            *_bed_tail(),
        ),
        min_area_m2=9.0,
    ),
    Archetype(
        "br_bed_corner",
        "bedroom",
        "Bed in the corner of a small room",
        (
            Slot("bed", ("bed",), InCorner(WallPick("any", prefer="long")), required=True),
            Slot("nightstand_left", ("nightstand",), Beside("bed", "either")),
            Slot("wardrobe", ("wardrobe",), AgainstWall(WallPick("other", "bed"), centered=False)),
            Slot(
                "study_desk", ("study_desk",), AgainstWall(WallPick("other", "bed"), centered=False)
            ),
            Slot("desk_chair", ("desk_chair",), InFront("study_desk", (0.0, 0.10))),
            *_bed_tail(),
        ),
    ),
    Archetype(
        "br_bed_study",
        "bedroom",
        "Bed with a study desk by the window",
        (
            Slot("bed", ("bed",), AgainstWall(BED_WALL), required=True),
            Slot(
                "study_desk",
                ("study_desk",),
                AgainstWall(WallPick("window"), centered=False),
                required=True,
            ),
            Slot("desk_chair", ("desk_chair",), InFront("study_desk", (0.0, 0.10))),
            Slot("nightstand_left", ("nightstand",), Beside("bed", "either")),
            Slot("wardrobe", ("wardrobe",), AgainstWall(WallPick("other", "bed"), centered=False)),
            *_bed_tail(),
        ),
        min_area_m2=9.5,
    ),
    Archetype(
        "br_dresser_opposite",
        "bedroom",
        "Bed facing a dresser, wardrobe beside",
        (
            Slot("bed", ("bed",), AgainstWall(BED_WALL), required=True),
            Slot(
                "dresser",
                ("dresser", "chest_of_drawers"),
                AgainstWall(WallPick("opposite", "bed")),
                required=True,
            ),
            Slot("nightstand_left", ("nightstand",), Beside("bed", "left")),
            Slot("nightstand_right", ("nightstand",), Beside("bed", "right")),
            Slot("wardrobe", ("wardrobe",), AgainstWall(WallPick("beside", "bed"), centered=False)),
            *_bed_tail(),
        ),
        min_area_m2=11.0,
    ),
    Archetype(
        "br_wardrobe_opposite",
        "bedroom",
        "Wardrobe wall opposite the bed",
        (
            Slot("bed", ("bed",), AgainstWall(BED_WALL), required=True),
            Slot(
                "wardrobe", ("wardrobe",), AgainstWall(WallPick("opposite", "bed")), required=True
            ),
            Slot("nightstand_left", ("nightstand",), Beside("bed", "left")),
            Slot("nightstand_right", ("nightstand",), Beside("bed", "right")),
            Slot(
                "dresser",
                ("dresser", "chest_of_drawers"),
                AgainstWall(WallPick("beside", "bed"), centered=False),
            ),
            *_bed_tail(),
        ),
        min_area_m2=11.0,
    ),
    Archetype(
        "br_reading_nook",
        "bedroom",
        "Bed with a reading chair and lamp",
        (
            Slot("bed", ("bed",), AgainstWall(BED_WALL), required=True),
            Slot("nightstand_left", ("nightstand",), Beside("bed", "left")),
            Slot("nightstand_right", ("nightstand",), Beside("bed", "right")),
            Slot("armchair", CHAIRS, Corner(), required=True),
            Slot("floor_lamp", ("floor_lamp",), Corner(near="armchair")),
            Slot("wardrobe", ("wardrobe",), AgainstWall(WallPick("other", "bed"), centered=False)),
            *_bed_tail(),
        ),
        min_area_m2=11.0,
    ),
    Archetype(
        "br_window_headboard",
        "bedroom",
        "Low headboard under the window",
        (
            Slot("bed", ("bed",), AgainstWall(WallPick("window", prefer="long")), required=True),
            Slot("nightstand_left", ("nightstand",), Beside("bed", "left")),
            Slot("nightstand_right", ("nightstand",), Beside("bed", "right")),
            Slot("wardrobe", ("wardrobe",), AgainstWall(WallPick("other", "bed"), centered=False)),
            *_bed_tail(),
        ),
        min_area_m2=9.0,
    ),
    Archetype(
        "br_compact",
        "bedroom",
        "Compact room: bed in the corner, wardrobe and a bench",
        (
            Slot("bed", ("bed",), InCorner(WallPick("any", prefer="short")), required=True),
            Slot("wardrobe", ("wardrobe",), AgainstWall(WallPick("other", "bed"), centered=False)),
            Slot("nightstand_left", ("nightstand",), Beside("bed", "either")),
            Slot("bench", ("bench", "pouf"), InFront("bed", (0.05, 0.15))),
            Slot("ceiling_light", ("pendant_light", "ceiling_light"), Ceiling("bed")),
        ),
    ),
)

ARCHETYPES: dict[str, Archetype] = {a.key: a for a in (*LIVING, *BEDROOM)}


def for_space(space: str) -> tuple[Archetype, ...]:
    """Archetypes for a space type; none for spaces that do not get designs at launch."""
    return tuple(a for a in ARCHETYPES.values() if a.space == space)
