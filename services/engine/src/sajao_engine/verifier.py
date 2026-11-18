"""The verifier: an independent re-check of a finished Design.

It reads only the Design, the twin it builds on and the brief. It never trusts
the solver: every footprint is rebuilt from the product's catalog size grown by
its error band, every zone from the measured room grown by its bands, and every
hard rule is checked from scratch. A design passes only when every hard rule,
the budget and the stock check pass.

Hard rules (never relaxed): inside the room, inside the redo area, no overlaps,
door swings and approaches clear, window access, switchboard and AC access,
front clearance for seats, drawers and wardrobe doors, walkways of at least
60 cm from the door to everything that must be reached, only measured sizes in
tight spots, the twin edits match the items, and the total matches the items.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from sajao_engine.categories import Category, category
from sajao_engine.geometry import (
    Poly,
    Rect,
    edges,
    overlaps,
    point_in_polygon,
    point_segment_distance,
    polygon_distance,
    polygon_inside,
    segment_distance,
)
from sajao_engine.room import (
    FIT_CLAIM_LEVELS,
    Confidence,
    ObjectOverride,
    OpenEdge,
    Room,
    WallLine,
    high,
    room_from_twin,
)
from sajao_engine.walkway import AccessTarget, check_walkways, clearance
from sajao_schemas.generated.v1 import (
    AddEdit,
    Brief,
    CheckReport,
    Design,
    DesignItem,
    MoveEdit,
    RedoArea,
    RemoveEdit,
    ReplaceEdit,
    RotateEdit,
    RuleResult,
    SpaceTwin,
)

# Walkway widths, in metres. 60 cm is never relaxed; 75 cm is preferred and scored.
WALKWAY_MIN_M = 0.60
WALKWAY_PREFERRED_M = 0.75
# Seats need knee room in front, whatever their category says about drawers.
SEAT_FRONT_CLEARANCE_M = 0.30
# Free space on both sides of an axis smaller than this makes a tight spot.
TIGHT_M = 0.05
# A wall item counts as on a wall when its center is this close to the wall line.
WALL_ITEM_REACH_M = 0.15
# Floating point slack for positions rounded to the millimetre.
TOL_M = 5e-4

HARD_RULES = (
    "twin_matches_items",
    "total_matches_items",
    "inside_room",
    "inside_redo_area",
    "no_overlap",
    "door_clear",
    "window_access",
    "fixture_access",
    "front_clearance",
    "wall_items_clear",
    "walkway_min",
    "tight_spots_measured",
)


@dataclass(frozen=True)
class Violation:
    rule: str
    item_ids: tuple[str, ...]
    detail: str


@dataclass(frozen=True)
class Placed:
    """A design item as the verifier rebuilds it."""

    id: str
    cat: Category
    footprint: Rect
    height_m: float
    dims_measured: tuple[bool, bool]  # width, depth

    @property
    def poly(self) -> Poly:
        return self.footprint.corners()


@dataclass(frozen=True)
class ItemFit:
    """One item's fit, written by the verifier, never by a model."""

    status: Literal["fits", "tight", "does_not_fit"]
    # Clearance left after every error band is taken as margin, in metres.
    spare_m: float


@dataclass
class Verification:
    report: CheckReport
    violations: list[Violation]
    confidence: Confidence = "estimated"
    # Smallest gap from each design item to a wall or another footprint, in metres.
    item_gaps_m: dict[str, float] = field(default_factory=dict)
    # Per-item fit for floor items. Empty unless the room is taped or AR-measured:
    # an estimated room is verified with its bands as margin, but no fit is claimed.
    item_fits: dict[str, ItemFit] = field(default_factory=dict)

    @property
    def fit_claims(self) -> bool:
        return self.confidence in FIT_CLAIM_LEVELS

    @property
    def passed(self) -> bool:
        return self.report.passed


def _placed(item: DesignItem) -> Placed:
    dims = item.product.dimensions
    return Placed(
        id=item.id,
        cat=category(item.product.category),
        footprint=Rect(
            item.position.x_m,
            item.position.y_m,
            high(dims.width),
            high(dims.depth),
            item.rotation_deg,
        ),
        height_m=high(dims.height),
        dims_measured=(dims.width.source == "measured", dims.depth.source == "measured"),
    )


def room_for_design(
    design: Design,
    twin: SpaceTwin,
    redo: RedoArea | None = None,
    confidence: Confidence | None = None,
) -> Room:
    """The room with the design's twin edits applied to what was already there."""
    removed: list[str] = []
    overrides: dict[str, ObjectOverride] = {}
    for edit in design.twin.edits if design.twin else []:
        if isinstance(edit, RemoveEdit):
            removed.append(edit.object_id)
        elif isinstance(edit, MoveEdit):
            prev = overrides.get(edit.object_id, ObjectOverride())
            overrides[edit.object_id] = ObjectOverride(
                edit.to.x_m, edit.to.y_m, prev.yaw_deg, prev.size
            )
        elif isinstance(edit, RotateEdit):
            prev = overrides.get(edit.object_id, ObjectOverride())
            overrides[edit.object_id] = ObjectOverride(prev.x_m, prev.y_m, edit.yaw_deg, prev.size)
        elif isinstance(edit, ReplaceEdit):
            prev = overrides.get(edit.object_id, ObjectOverride())
            size = (edit.product_size.width, edit.product_size.depth, edit.product_size.height)
            overrides[edit.object_id] = ObjectOverride(prev.x_m, prev.y_m, prev.yaw_deg, size)
    polygon = redo.polygon if redo is not None and redo.scope == "part" else None
    return room_from_twin(
        twin,
        removed=removed,
        overrides=overrides,
        redo=[(p.x_m, p.y_m) for p in polygon] if polygon else None,
        confidence=confidence,
    )


def _check_twin(design: Design, twin: SpaceTwin) -> list[Violation]:
    if design.twin is None:
        return [Violation("twin_matches_items", (), "The design does not point at a twin.")]
    out: list[Violation] = []
    if design.twin.twin_id != twin.id or design.twin.twin_version != twin.version:
        out.append(
            Violation("twin_matches_items", (), "The design points at another twin or version.")
        )
    adds = [e for e in design.twin.edits if isinstance(e, AddEdit)]
    unmatched = list(adds)
    for item in design.items:
        match = next(
            (
                e
                for e in unmatched
                if e.product_id == str(item.product.id)
                and math.dist((e.to.x_m, e.to.y_m), (item.position.x_m, item.position.y_m)) <= 1e-3
                and abs(((e.yaw_deg - item.rotation_deg + 180.0) % 360.0) - 180.0) <= 0.5
            ),
            None,
        )
        if match is None:
            out.append(
                Violation(
                    "twin_matches_items",
                    (item.id,),
                    "No add edit matches this item's product and pose.",
                )
            )
        else:
            unmatched.remove(match)
    for add in unmatched:
        out.append(Violation("twin_matches_items", (), f"Add edit {add.id} has no matching item."))
    known = {o.id for o in twin.objects}
    for edit in design.twin.edits:
        target = getattr(edit, "object_id", None)
        if target is not None and target not in known:
            out.append(
                Violation(
                    "twin_matches_items", (), f"Edit {edit.id} names an object the twin lacks."
                )
            )
    return out


def _wall_item_ok(p: Placed, room: Room) -> tuple[bool, str]:
    """On a wall, inside its span, clear of doors and of windows bar curtains."""
    c = p.footprint.center
    half = p.footprint.width / 2.0
    for w in room.walls:
        if point_segment_distance(c, w.a, w.b) > WALL_ITEM_REACH_M:
            continue
        dx, dy = w.direction
        s = (c[0] - w.a[0]) * dx + (c[1] - w.a[1]) * dy
        if s - half < -TOL_M or s + half > w.length + TOL_M:
            return False, f"runs past the end of wall {w.id}"
        for o in room.openings:
            if o.wall_id != w.id or (o.kind == "window" and p.cat.key == "curtains"):
                continue
            if s + half > o.s0 + TOL_M and s - half < o.s1 - TOL_M:
                return False, f"covers {o.kind} {o.id}"
        return True, ""
    return False, "is not on a wall"


def verify(
    design: Design,
    twin: SpaceTwin,
    brief: Brief,
    *,
    redo: RedoArea | None = None,
    checked_at: datetime,
    confidence: Confidence | None = None,
) -> Verification:
    """Re-check a design. Pure: the same inputs give the same report."""
    room = room_for_design(design, twin, redo, confidence)
    placed = [_placed(item) for item in design.items]
    floor = [p for p in placed if p.cat.mount == "floor"]
    rugs = [p for p in placed if p.cat.mount == "rug"]
    kept_floor = [o for o in room.obstacles if o.mount == "floor"]
    kept_rugs = [o for o in room.obstacles if o.mount == "rug"]
    v: list[Violation] = []

    v += _check_twin(design, twin)

    total = sum(item.product.price.amount_minor for item in design.items)
    if design.total_cost.amount_minor != total:
        v.append(
            Violation(
                "total_matches_items",
                (),
                f"Total {design.total_cost.amount_minor} is not the item sum {total}.",
            )
        )

    # Inside the room, with each wall's margin.
    for p in floor + rugs:
        poly = p.poly
        if not polygon_inside(poly, room.floor):
            v.append(Violation("inside_room", (p.id,), "Leaves the floor."))
            continue
        for w in room.walls:
            if wall_gap(poly, w) + TOL_M < w.margin_m:
                v.append(
                    Violation(
                        "inside_room",
                        (p.id,),
                        f"Closer to wall {w.id} than its {w.margin_m * 100:.0f} cm error band.",
                    )
                )
                break
        # An open edge is not a wall, but the design stays in this area by the edge's band.
        for i, e in enumerate(room.open_edges):
            if wall_gap(poly, e) + TOL_M < e.margin_m:
                v.append(
                    Violation(
                        "inside_room",
                        (p.id,),
                        f"Closer to open edge {i + 1} than its {e.margin_m * 100:.0f} cm band.",
                    )
                )
                break
    for p in placed:
        if p.cat.mount in ("ceiling", "surface") and not point_in_polygon(
            p.footprint.center, room.floor
        ):
            v.append(Violation("inside_room", (p.id,), "Hangs or sits outside the room."))

    if room.redo is not None:
        for p in placed:
            inside = (
                polygon_inside(p.poly, room.redo)
                if p.cat.mount in ("floor", "rug")
                else point_in_polygon(p.footprint.center, room.redo)
            )
            if not inside:
                v.append(
                    Violation("inside_redo_area", (p.id,), "Outside the part you chose to redo.")
                )

    # Overlaps: floor items with each other and with what stays; rugs with rugs.
    for i, a in enumerate(floor):
        for b in floor[i + 1 :]:
            if overlaps(a.poly, b.poly):
                v.append(Violation("no_overlap", (a.id, b.id), "Overlap."))
        for o in kept_floor:
            if overlaps(a.poly, o.footprint.corners()):
                v.append(Violation("no_overlap", (a.id,), f"Overlaps {o.label} that stays."))
    for i, a in enumerate(rugs):
        for b in rugs[i + 1 :]:
            if overlaps(a.poly, b.poly):
                v.append(Violation("no_overlap", (a.id, b.id), "Rugs overlap."))
        for o in kept_rugs:
            if overlaps(a.poly, o.footprint.corners()):
                v.append(Violation("no_overlap", (a.id,), f"Overlaps {o.label} that stays."))

    # Doors: nothing in the swing; nothing but rugs in the approach.
    for door in room.doors:
        for p in floor + rugs:
            if door.swing is not None and overlaps(p.poly, door.swing):
                v.append(Violation("door_clear", (p.id,), f"In the swing of door {door.id}."))
            elif p.cat.mount == "floor" and overlaps(p.poly, door.approach.corners()):
                v.append(Violation("door_clear", (p.id,), f"Blocks the way in at door {door.id}."))

    for win in room.windows:
        for p in floor:
            if p.height_m > win.clear_above_m + TOL_M and overlaps(p.poly, win.approach.corners()):
                v.append(
                    Violation(
                        "window_access",
                        (p.id,),
                        f"Stands in front of window {win.id} above its sill.",
                    )
                )

    for fx in room.fixtures:
        for p in floor:
            if p.height_m > fx.clear_above_m + TOL_M and overlaps(p.poly, fx.zone.corners()):
                v.append(
                    Violation(
                        "fixture_access",
                        (p.id,),
                        f"Blocks the {fx.kind.replace('_', ' ')} {fx.id}.",
                    )
                )

    # Front clearance: wardrobe doors and drawers open, and seats have knee room.
    others: list[tuple[str, Poly]] = [(p.id, p.poly) for p in floor] + [
        (o.id, o.footprint.corners()) for o in kept_floor
    ]
    for p in floor:
        depth = max(p.cat.opening_clearance_m, SEAT_FRONT_CLEARANCE_M if p.cat.seating else 0.0)
        if depth <= 0:
            continue
        strip = p.footprint.strip("front", depth).corners()
        for oid, poly in others:
            if oid != p.id and overlaps(strip, poly):
                v.append(
                    Violation(
                        "front_clearance",
                        (p.id, oid),
                        f"Needs {depth * 100:.0f} cm clear in front.",
                    )
                )
        if not polygon_inside(strip, room.floor):
            v.append(
                Violation(
                    "front_clearance",
                    (p.id,),
                    f"Needs {depth * 100:.0f} cm clear in front; a wall is in the way.",
                )
            )

    for p in placed:
        if p.cat.mount == "wall":
            ok, why = _wall_item_ok(p, room)
            if not ok:
                v.append(Violation("wall_items_clear", (p.id,), f"Wall item {why}."))

    # Walkways.
    footprints = [p.poly for p in floor] + [o.footprint.corners() for o in kept_floor]
    targets = _access_targets(floor, room)
    gaps = clearance(room, footprints)
    walk = check_walkways(room, footprints, targets, WALKWAY_MIN_M, precomputed=gaps)
    if not walk.doors_connected:
        v.append(
            Violation(
                "walkway_min",
                (),
                "No 60 cm walkway joins the doors and open sides: "
                + ", ".join(walk.unreached_doors or ("blocked",))
                + ".",
            )
        )
    for tid in walk.unreached_items:
        v.append(Violation("walkway_min", (tid,), "Cannot be reached by a 60 cm walkway."))
    preferred = check_walkways(room, footprints, targets, WALKWAY_PREFERRED_M, precomputed=gaps)

    # Tight spots take only measured sizes.
    item_gaps: dict[str, float] = {}
    blockers = [o.footprint.corners() for o in kept_floor]
    for p in floor:
        neighbours = [q.poly for q in floor if q.id != p.id] + blockers
        item_gaps[p.id] = _min_gap(p.poly, neighbours, room)
        for axis, sides in ((0, ("left", "right")), (1, ("front", "back"))):
            if p.dims_measured[axis]:
                continue
            if all(
                _side_blocked(p.footprint.strip(side, TIGHT_M), neighbours, room) for side in sides
            ):
                v.append(
                    Violation(
                        "tight_spots_measured",
                        (p.id,),
                        "Fits a tight spot on an estimated size; it needs a measured size.",
                    )
                )
                break

    budget_ok = _budget_ok(total, brief)
    stock_ok = all(item.product.in_stock and item.product.routes for item in design.items)

    rules: list[RuleResult] = []
    for rule in HARD_RULES:
        found = [x for x in v if x.rule == rule]
        row: dict[str, object] = {"rule": rule, "kind": "hard", "passed": not found}
        detail = "; ".join(sorted({_describe(x) for x in found}))
        if detail:
            row["detail"] = detail
        rules.append(RuleResult.model_validate(row))
    soft: dict[str, object] = {
        "rule": "walkway_preferred",
        "kind": "soft",
        "passed": preferred.passed,
        "score": 1.0 if preferred.passed else 0.0,
    }
    if not preferred.passed:
        soft["detail"] = "Some walkways are under 75 cm."
    rules.append(RuleResult.model_validate(soft))
    passed = not v and budget_ok and stock_ok
    report = CheckReport(
        passed=passed, checked_at=checked_at, rules=rules, budget_ok=budget_ok, stock_ok=stock_ok
    )
    fits: dict[str, ItemFit] = {}
    if room.fit_claims:
        failing = {i for x in v for i in x.item_ids}
        for pid, gap in item_gaps.items():
            status: Literal["fits", "tight", "does_not_fit"] = (
                "does_not_fit" if pid in failing else "tight" if gap < TIGHT_M else "fits"
            )
            fits[pid] = ItemFit(status, round(gap, 3))
    return Verification(
        report=report,
        violations=v,
        confidence=room.confidence,
        item_gaps_m=item_gaps,
        item_fits=fits,
    )


def wall_gap(poly: Poly, wall: WallLine | OpenEdge) -> float:
    """Distance from a footprint to a wall line."""
    return min(segment_distance(a, b, wall.a, wall.b) for a, b in edges(poly))


def _describe(x: Violation) -> str:
    return f"{', '.join(x.item_ids)}: {x.detail}" if x.item_ids else x.detail


def _budget_ok(total: int, brief: Brief) -> bool:
    limit = brief.budget.limit.amount_minor
    if brief.budget.flexibility == "strict":
        return total <= limit
    return total * 10 <= limit * 11


def _side_blocked(strip: Rect, neighbours: Sequence[Poly], room: Room) -> bool:
    """A side is blocked by a wall or a footprint; the floor runs on past an open edge."""
    poly = strip.corners()
    if any(wall_gap(poly, w) < w.margin_m - TOL_M for w in room.walls):
        return True
    return any(overlaps(poly, n) for n in neighbours)


def _min_gap(poly: Poly, neighbours: Sequence[Poly], room: Room) -> float:
    gaps = [polygon_distance(poly, n) for n in neighbours]
    for w in room.walls:
        gaps.append(wall_gap(poly, w) - w.margin_m)
    return max(0.0, min(gaps)) if gaps else math.inf


def _access_targets(floor: Sequence[Placed], room: Room) -> list[AccessTarget]:
    targets: list[AccessTarget] = []
    for p in floor:
        if not p.cat.access:
            continue
        strips = tuple(p.footprint.strip(side, 0.10).corners() for side in p.cat.access)
        targets.append(AccessTarget(p.id, strips, p.cat.any_side))
    for o in room.obstacles:
        cat = category(o.category)
        if o.mount != "floor" or o.built_in or not cat.access:
            continue
        # The scan does not know which way a kept item faces: any side will do.
        strips = tuple(
            o.footprint.strip(side, 0.10).corners() for side in ("front", "back", "left", "right")
        )
        targets.append(AccessTarget(o.id, strips, True))
    return targets
