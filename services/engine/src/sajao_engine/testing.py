"""Fixture rooms, products and designs for tests and offline runs.

The rooms are the commonest Indian flat layouts at their usual sizes. Every one
is a full ``SpaceTwin`` that validates against the contract, built on the
schema's own twin fixture so the shape stays in step with the contract.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from sajao_schemas.generated.v1 import Brief, Design, Product, SpaceTwin

SCHEMA_FIXTURES = (
    Path(__file__).resolve().parents[4] / "packages" / "schemas" / "fixtures" / "v1" / "valid"
)
WHEN = "2026-01-05T10:00:00Z"
NS = uuid.UUID("5a1a0000-0000-4000-8000-000000000000")


def dim(value: float, band: float = 0.01, source: str = "measured") -> dict[str, Any]:
    return {"value_m": value, "source": source, "error_band_m": band}


def est(value: float, band: float = 0.05) -> dict[str, Any]:
    return dim(value, band, "estimated")


def load_schema_fixture(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((SCHEMA_FIXTURES / f"{name}.json").read_text())
    return data


@dataclass(frozen=True)
class OpeningSpec:
    id: str
    kind: Literal["door", "window"]
    wall: int  # index into the walls, counterclockwise from the wall along y = 0
    offset: float
    width: float
    hinge: Literal["start", "end"] | None = None
    opens: Literal["inward", "outward"] | None = None
    sill: float | None = None


@dataclass(frozen=True)
class FixtureSpec:
    id: str
    kind: Literal["switchboard", "socket", "ac_unit"]
    wall: int
    offset: float
    mount: float
    width: float | None = None


def twin_from_polygon(
    name: str,
    corners: Sequence[tuple[float, float]],
    *,
    space_type: str = "living_room",
    openings: Iterable[OpeningSpec] = (),
    fixtures: Iterable[FixtureSpec] = (),
    band: float = 0.08,
    measured: bool = False,
    objects: Sequence[dict[str, Any]] = (),
    built_ins: Sequence[dict[str, Any]] = (),
    open_edges: Iterable[int] = (),
    open_spans: Mapping[int, tuple[float, float]] | None = None,
) -> SpaceTwin:
    """A twin whose shell is the counterclockwise polygon ``corners``.

    Edge ``i`` runs from corner ``i`` to the next and carries wall ``w{i+1}``, unless
    it is in ``open_edges`` (no wall: the area runs on into the next one) or has an
    open span (s0, s1) along it, which leaves walls ``w{i+1}`` before and
    ``w{i+1}b`` after the span (an archway with no door).
    """
    base = load_schema_fixture("space-twin")
    open_set = set(open_edges)
    spans = dict(open_spans or {})

    def length_dim(v: float) -> dict[str, Any]:
        return dim(v, 0.01) if measured else est(v, band)

    def wall(wid: str, a: tuple[float, float], b: tuple[float, float]) -> dict[str, Any]:
        length = round(((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5, 4)
        return {
            "id": wid,
            "start": {"x_m": a[0], "y_m": a[1]},
            "end": {"x_m": b[0], "y_m": b[1]},
            "length": length_dim(length),
        }

    walls = []
    for i, a in enumerate(corners):
        b = corners[(i + 1) % len(corners)]
        if i in open_set:
            continue
        if i in spans:
            s0, s1 = spans[i]
            total = ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5
            ux, uy = (b[0] - a[0]) / total, (b[1] - a[1]) / total
            p = (round(a[0] + ux * s0, 4), round(a[1] + uy * s0, 4))
            q = (round(a[0] + ux * s1, 4), round(a[1] + uy * s1, 4))
            walls.append(wall(f"w{i + 1}", a, p))
            walls.append(wall(f"w{i + 1}b", q, b))
            continue
        walls.append(wall(f"w{i + 1}", a, b))
    shell_openings = []
    for o in openings:
        item: dict[str, Any] = {
            "id": o.id,
            "kind": o.kind,
            "wall_id": f"w{o.wall + 1}",
            "offset": est(o.offset, 0.03),
            "width": est(o.width, 0.03),
            "height": est(2.05 if o.kind == "door" else 1.2, 0.03),
        }
        if o.kind == "door" and o.hinge and o.opens:
            item["swing"] = {"hinge": o.hinge, "opens": o.opens}
        if o.sill is not None:
            item["sill_height"] = est(o.sill, 0.03)
        shell_openings.append(item)
    shell_fixtures = []
    for f in fixtures:
        fx: dict[str, Any] = {
            "id": f.id,
            "kind": f.kind,
            "wall_id": f"w{f.wall + 1}",
            "offset": est(f.offset, 0.03),
            "mount_height": est(f.mount, 0.03),
        }
        if f.width is not None:
            fx["width"] = est(f.width, 0.03)
        shell_fixtures.append(fx)
    base["id"] = str(uuid.uuid5(NS, f"twin:{name}"))
    base["space_type"] = space_type
    base["shell"]["floor_polygon"] = [{"x_m": x, "y_m": y} for x, y in corners]
    base["shell"]["walls"] = walls
    base["shell"]["openings"] = shell_openings
    base["shell"]["fixtures"] = shell_fixtures
    base["shell"]["surfaces"] = [{"id": w["id"], "kind": "wall"} for w in walls] + [
        {"id": "floor", "kind": "floor"},
        {"id": "ceiling", "kind": "ceiling"},
    ]
    base["shell"]["built_ins"] = list(built_ins)
    if measured:
        base["shell"]["ceiling_height"] = dim(base["shell"]["ceiling_height"]["value_m"], 0.01)
    base["objects"] = list(objects)
    base["confidence"] = (
        {"level": "taped", "basis": "tape"}
        if measured
        else {"level": "estimated", "basis": "depth_model"}
    )
    base.pop("areas", None)
    return SpaceTwin.model_validate(base)


def rect(w: float, d: float) -> list[tuple[float, float]]:
    return [(0.0, 0.0), (w, 0.0), (w, d), (0.0, d)]


def fixture_rooms() -> dict[str, SpaceTwin]:
    """The fixture rooms by name. Wall 0 runs along y = 0; walls go counterclockwise."""
    rooms = {
        # 11 x 15 ft hall in a 2BHK: main door near a corner, balcony door on the far short wall.
        "lr_2bhk_hall": twin_from_polygon(
            "lr_2bhk_hall",
            rect(3.35, 4.6),
            openings=[
                OpeningSpec("main", "door", 3, 0.10, 1.0, "end", "inward"),
                OpeningSpec("balcony", "door", 1, 3.35 - 0.3 - 1.5, 1.5),
                OpeningSpec("win", "window", 2, 1.4, 1.5, sill=0.9),
            ],
            fixtures=[
                FixtureSpec("sb", "switchboard", 3, 1.25, 1.3),
                FixtureSpec("ac", "ac_unit", 0, 1.2, 2.2, 0.9),
            ],
        ),
        # 10 x 12 ft hall in a compact 1BHK.
        "lr_1bhk_compact": twin_from_polygon(
            "lr_1bhk_compact",
            rect(3.05, 3.65),
            openings=[
                OpeningSpec("main", "door", 0, 0.10, 0.95, "start", "inward"),
                OpeningSpec("inner", "door", 1, 2.6, 0.8),
                OpeningSpec("win", "window", 2, 0.8, 1.2, sill=0.9),
            ],
            fixtures=[FixtureSpec("sb", "switchboard", 0, 1.15, 1.3)],
        ),
        # 14 x 18 ft hall in a 3BHK with a passage to the bedrooms.
        "lr_3bhk_large": twin_from_polygon(
            "lr_3bhk_large",
            rect(4.25, 5.5),
            openings=[
                OpeningSpec("main", "door", 0, 0.15, 1.05, "start", "inward"),
                OpeningSpec("passage", "door", 2, 0.2, 1.0),
                OpeningSpec("win1", "window", 1, 1.5, 1.8, sill=0.75),
                OpeningSpec("win2", "window", 3, 3.0, 1.2, sill=0.9),
            ],
            fixtures=[
                FixtureSpec("sb", "switchboard", 0, 1.3, 1.3),
                FixtureSpec("ac", "ac_unit", 3, 0.6, 2.2, 1.0),
            ],
        ),
        # L-shaped hall where the dining nook steps in.
        "lr_l_shape": twin_from_polygon(
            "lr_l_shape",
            [(0.0, 0.0), (4.6, 0.0), (4.6, 3.2), (3.0, 3.2), (3.0, 5.0), (0.0, 5.0)],
            openings=[
                OpeningSpec("main", "door", 5, 0.2, 1.0, "start", "inward"),
                OpeningSpec("win", "window", 1, 0.9, 1.5, sill=0.9),
                OpeningSpec("kitchen", "door", 4, 0.3, 0.9),
            ],
            fixtures=[FixtureSpec("sb", "switchboard", 5, 1.35, 1.3)],
        ),
        # 11 x 13 ft master bedroom: door in a corner, attached bath, window opposite the door.
        "br_master": twin_from_polygon(
            "br_master",
            rect(3.35, 3.95),
            space_type="bedroom",
            openings=[
                OpeningSpec("door", "door", 0, 0.10, 0.9, "start", "inward"),
                OpeningSpec("bath", "door", 1, 0.15, 0.75, "start", "inward"),
                OpeningSpec("win", "window", 2, 1.0, 1.5, sill=0.9),
            ],
            fixtures=[
                FixtureSpec("sb", "switchboard", 0, 1.1, 1.3),
                FixtureSpec("ac", "ac_unit", 3, 1.5, 2.2, 1.0),
            ],
        ),
        # 10 x 11 ft second bedroom.
        "br_standard": twin_from_polygon(
            "br_standard",
            rect(3.05, 3.35),
            space_type="bedroom",
            openings=[
                OpeningSpec("door", "door", 0, 0.10, 0.85, "start", "inward"),
                OpeningSpec("win", "window", 1, 1.0, 1.2, sill=0.9),
            ],
            fixtures=[FixtureSpec("sb", "switchboard", 0, 1.05, 1.3)],
        ),
        # 9 x 10 ft small bedroom.
        "br_small": twin_from_polygon(
            "br_small",
            rect(2.75, 3.05),
            space_type="bedroom",
            openings=[
                OpeningSpec("door", "door", 3, 0.10, 0.8, "end", "inward"),
                OpeningSpec("win", "window", 1, 0.8, 1.2, sill=0.9),
            ],
            fixtures=[FixtureSpec("sb", "switchboard", 3, 1.0, 1.3)],
        ),
    }
    rooms.update(open_plan_rooms())
    rooms["schema_fixture"] = SpaceTwin.model_validate(load_schema_fixture("space-twin"))
    return rooms


def open_plan_rooms() -> dict[str, SpaceTwin]:
    """Rooms whose floor edges are not all walls: open plan, an archway, L shapes."""
    return {
        # Living area open to the dining area along its whole far side.
        "lr_open_plan": twin_from_polygon(
            "lr_open_plan",
            rect(4.0, 4.6),
            openings=[
                OpeningSpec("main", "door", 3, 3.4, 1.0, "start", "inward"),
                OpeningSpec("win", "window", 1, 1.4, 1.5, sill=0.9),
            ],
            fixtures=[FixtureSpec("sb", "switchboard", 3, 2.8, 1.3)],
            open_edges=[2],
        ),
        # The first real scan's shape: an L-shaped open living area, its kitchen side open.
        "lr_open_l": twin_from_polygon(
            "lr_open_l",
            [(0.0, 0.0), (5.5, 0.0), (5.5, 3.2), (3.2, 3.2), (3.2, 6.0), (0.0, 6.0)],
            openings=[
                OpeningSpec("main", "door", 0, 0.2, 1.0, "start", "inward"),
                OpeningSpec("win", "window", 1, 1.0, 1.5, sill=0.9),
                OpeningSpec("win2", "window", 5, 1.2, 1.2, sill=0.9),
            ],
            fixtures=[FixtureSpec("sb", "switchboard", 0, 1.35, 1.3)],
            open_edges=[4],
        ),
        # A hall whose side wall has a 1.4 m archway with no door.
        "lr_archway": twin_from_polygon(
            "lr_archway",
            rect(3.6, 4.8),
            openings=[
                OpeningSpec("main", "door", 0, 0.15, 1.0, "start", "inward"),
                OpeningSpec("win", "window", 2, 1.2, 1.5, sill=0.9),
            ],
            fixtures=[FixtureSpec("sb", "switchboard", 0, 1.35, 1.3)],
            open_spans={1: (2.6, 4.0)},
        ),
        # L-shaped bedroom with a dressing nook.
        "br_l_shape": twin_from_polygon(
            "br_l_shape",
            [(0.0, 0.0), (3.6, 0.0), (3.6, 3.0), (2.4, 3.0), (2.4, 4.0), (0.0, 4.0)],
            space_type="bedroom",
            openings=[
                OpeningSpec("door", "door", 0, 0.1, 0.85, "start", "inward"),
                OpeningSpec("win", "window", 1, 0.9, 1.2, sill=0.9),
            ],
            fixtures=[FixtureSpec("sb", "switchboard", 0, 1.05, 1.3)],
        ),
    }


def product(
    category: str,
    width: float,
    depth: float,
    height: float,
    *,
    price_rupees: int = 10_000,
    measured: bool = True,
    band: float | None = None,
    key: str | None = None,
    in_stock: bool = True,
) -> Product:
    """A catalog product with a real-looking contract shape."""
    base = load_schema_fixture("product")
    b = band if band is not None else (0.01 if measured else 0.03)
    make = dim if measured else est
    name = key or f"{category}-{width}-{depth}-{height}"
    base["id"] = str(uuid.uuid5(NS, f"product:{name}"))
    base["sku"] = name.upper()
    base["title"] = name.replace("_", " ")
    base["category"] = category
    base["group"] = (
        "lighting"
        if "lamp" in category or "light" in category
        else (
            "decor"
            if category in {"rug", "art", "plant", "mirror", "curtains", "vase", "cushion"}
            else "furniture"
        )
    )
    base["dimensions"] = {
        "width": make(width, b),
        "depth": make(depth, b),
        "height": make(height, b),
    }
    base["price"] = {"currency": "INR", "amount_minor": price_rupees * 100}
    base["in_stock"] = in_stock
    for route in base["routes"]:
        route["price"] = {"currency": "INR", "amount_minor": price_rupees * 100}
    return Product.model_validate(base)


def brief(
    twin: SpaceTwin,
    *,
    budget_rupees: int = 300_000,
    flexibility: str = "strict",
    vastu: bool = False,
    keep: Sequence[str] = (),
) -> Brief:
    base = load_schema_fixture("brief")
    base["id"] = str(uuid.uuid5(NS, f"brief:{twin.id}"))
    base["intent"] = "full_makeover"
    base["budget"] = {
        "limit": {"currency": "INR", "amount_minor": budget_rupees * 100},
        "flexibility": flexibility,
    }
    base["must_haves"] = []
    base["keep_item_ids"] = list(keep)
    base["consider_vastu"] = vastu
    return Brief.model_validate(base)


@dataclass(frozen=True)
class Pose:
    item_id: str
    product: Product
    x: float
    y: float
    rotation: float = 0.0


def design(
    twin: SpaceTwin,
    poses: Sequence[Pose],
    *,
    remove: Sequence[str] | None = None,
    archetype: str = "test",
) -> Design:
    """A design from hand-set poses. Every twin object is removed unless ``remove`` names some."""
    removed = [o.id for o in twin.objects] if remove is None else list(remove)
    base = load_schema_fixture("design")
    edits: list[dict[str, Any]] = [
        {"id": f"rm-{oid}"[:40], "op": "remove", "by": "solver", "object_id": oid}
        for oid in removed
    ]
    items = []
    for p in poses:
        dims = p.product.dimensions
        items.append(
            {
                "id": p.item_id,
                "product": p.product.model_dump(mode="json", exclude_unset=True),
                "position": {"x_m": p.x, "y_m": p.y},
                "rotation_deg": p.rotation,
                "placed_by": "solver",
            }
        )
        edits.append(
            {
                "id": f"add-{p.item_id}"[:40],
                "op": "add",
                "by": "solver",
                "product_id": str(p.product.id),
                "product_size": dims.model_dump(mode="json"),
                "to": {"x_m": p.x, "y_m": p.y, "z_m": 0.0},
                "yaw_deg": p.rotation,
                "label": p.product.title,
            }
        )
    base["id"] = str(uuid.uuid5(NS, f"design:{twin.id}:{archetype}"))
    base["archetype"] = archetype
    base["items"] = items
    base["relaxations"] = []
    base["explanations"] = []
    base["total_cost"] = {
        "currency": "INR",
        "amount_minor": sum(p.product.price.amount_minor for p in poses),
    }
    base["check_report"] = {
        "passed": False,
        "checked_at": WHEN,
        "rules": [],
        "budget_ok": False,
        "stock_ok": False,
    }
    base["twin"] = {"twin_id": str(twin.id), "twin_version": twin.version, "edits": edits}
    return Design.model_validate(base)


def living_kit(*, small: bool = False) -> dict[str, Product]:
    """A typical product per living-room slot, at common Indian catalog sizes."""
    sofa = (
        product("loveseat", 1.5, 0.85, 0.85, key="loveseat")
        if small
        else product("sofa", 2.0, 0.88, 0.85, price_rupees=42_000, key="sofa-3s")
    )
    chair = product("armchair", 0.72, 0.75, 0.8, price_rupees=14_000, key="armchair")
    return {
        "sofa": sofa,
        "diwan": product("diwan", 1.9, 0.8, 0.45, price_rupees=18_000, key="diwan"),
        "tv_unit": product(
            "tv_unit", 1.5 if small else 1.8, 0.4, 0.5, price_rupees=16_000, key="tv-unit"
        ),
        "coffee_table": product(
            "coffee_table", 0.9, 0.5, 0.42, price_rupees=8_000, key="coffee-table"
        ),
        "rug": product("rug", 1.6, 2.3, 0.01, price_rupees=7_000, key="rug-160", measured=False),
        "side_table": product("side_table", 0.45, 0.45, 0.55, price_rupees=3_500, key="side-table"),
        "floor_lamp": product("floor_lamp", 0.35, 0.35, 1.55, price_rupees=4_500, key="floor-lamp"),
        "art": product("art", 0.9, 0.04, 0.6, price_rupees=3_000, key="art-90"),
        "armchair": chair,
        "armchair_left": chair,
        "armchair_right": product(
            "armchair", 0.72, 0.75, 0.8, price_rupees=14_000, key="armchair-2"
        ),
        "pouf": product("pouf", 0.45, 0.45, 0.42, price_rupees=2_500, key="pouf"),
        "sideboard": product("sideboard", 1.2, 0.4, 0.8, price_rupees=19_000, key="sideboard"),
        "bookshelf": product("bookshelf", 0.8, 0.32, 1.8, price_rupees=9_000, key="bookshelf"),
        "plant": product("plant", 0.4, 0.4, 1.1, price_rupees=1_800, key="plant", measured=False),
        "ceiling_light": product(
            "pendant_light", 0.45, 0.45, 0.6, price_rupees=3_200, key="pendant"
        ),
    }


def sectional_kit() -> dict[str, Product]:
    kit = living_kit()
    kit["sofa"] = product("sectional_sofa", 2.4, 1.6, 0.85, price_rupees=65_000, key="sectional")
    return kit


def bedroom_kit(*, bed_width: float = 1.6) -> dict[str, Product]:
    """A typical product per bedroom slot: a queen bed by default."""
    stand = product("nightstand", 0.45, 0.4, 0.55, price_rupees=4_500, key="nightstand")
    return {
        "bed": product("bed", bed_width, 2.05, 0.95, price_rupees=32_000, key=f"bed-{bed_width}"),
        "nightstand_left": stand,
        "nightstand_right": product(
            "nightstand", 0.45, 0.4, 0.55, price_rupees=4_500, key="nightstand-2"
        ),
        "wardrobe": product("wardrobe", 1.2, 0.58, 2.0, price_rupees=28_000, key="wardrobe-2d"),
        "dresser": product("dresser", 0.9, 0.42, 0.8, price_rupees=12_000, key="dresser"),
        "study_desk": product("study_desk", 1.0, 0.5, 0.75, price_rupees=8_000, key="desk"),
        "desk_chair": product("desk_chair", 0.5, 0.5, 0.85, price_rupees=4_000, key="desk-chair"),
        "armchair": product("armchair", 0.7, 0.72, 0.8, price_rupees=12_000, key="armchair-br"),
        "floor_lamp": product("floor_lamp", 0.35, 0.35, 1.55, price_rupees=4_500, key="floor-lamp"),
        "rug": product("rug", 1.6, 2.3, 0.01, price_rupees=7_000, key="rug-160", measured=False),
        "art": product("art", 0.9, 0.04, 0.6, price_rupees=3_000, key="art-90"),
        "table_lamp": product("table_lamp", 0.25, 0.25, 0.45, price_rupees=1_800, key="table-lamp"),
        "ceiling_light": product(
            "ceiling_light", 0.5, 0.5, 0.15, price_rupees=2_800, key="ceiling-light"
        ),
        "plant": product(
            "plant", 0.35, 0.35, 0.9, price_rupees=1_500, key="plant-s", measured=False
        ),
        "bench": product("bench", 1.0, 0.4, 0.45, price_rupees=6_000, key="bench"),
    }
