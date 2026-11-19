"""Placement solver: products chosen for an archetype's slots in, a verified Design out.

Deterministic beam search. Slots are placed in archetype order; each rule
proposes candidate poses relative to the room or an earlier slot, cheap local
hard checks drop the impossible ones, and a soft score keeps the best few
partial layouts. Complete layouts are then handed, best first, to the
independent verifier; the first that passes becomes the Design. Every size
comes from the catalog plus its error band and every room number from the twin
plus its band, so the band is margin. No model is called and nothing is random.
"""

from __future__ import annotations

import math
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from sajao_engine import archetypes as A
from sajao_engine.categories import Category, category
from sajao_engine.geometry import (
    Poly,
    Rect,
    clip_convex,
    normalise_deg,
    overlaps,
    point_in_polygon,
    polygon_area,
    polygon_distance,
    polygon_inside,
)
from sajao_engine.room import Confidence, Room, WallLine, high, room_from_twin
from sajao_engine.verifier import (
    SEAT_FRONT_CLEARANCE_M,
    WALKWAY_MIN_M,
    WALL_ITEM_REACH_M,
    Verification,
    verify,
    wall_gap,
)
from sajao_engine.walkway import AccessTarget, check_walkways
from sajao_schemas.generated.v1 import Brief, Design, Product, RedoArea, SpaceTwin

STEP_M = 0.10
# What leaving out an optional item costs a layout, so placing beats dropping.
DROP_PENALTY = 1.5
SLOT_FLOOR = 1.2
BEAM = 8
# What a floor piece the photo does not show at all costs, against a rule score of 1.
OUT_OF_VIEW_WEIGHT = 1.0
PER_STATE = 6
# Keep this many poses per wall so the beam never bets everything on one wall.
PER_WALL = 2
FINALS = 6
# Coarse walkway check during the search; the verifier re-checks at its own resolution.
SEARCH_CELL_M = 0.05
# Pieces this large are checked for walkways as soon as they are placed.
LARGE_M2 = 0.0
# Positions sit this far inside every margin so millimetre rounding never touches a band.
SNUG_M = 0.002
# Wall items hang with their center at this height; ceiling items hang from the ceiling.
WALL_ITEM_CENTER_M = 1.45
NS = uuid.UUID("5a1a0000-0000-4000-8000-0000000000e1")


class SlotChoice(BaseModel):
    """A product the designer picked for one slot of the archetype."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    slot: str
    product: Product


class PlacementRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    twin: SpaceTwin
    brief: Brief
    redo: RedoArea | None = None
    # The floor a photo shows (photo-first rooms): new items' centres stay on it.
    in_view: list[tuple[float, float]] | None = None
    archetype: str
    choices: list[SlotChoice]
    design_id: uuid.UUID
    space_profile_id: uuid.UUID
    created_at: AwareDatetime
    intent: Literal["best_value", "best_match", "bold"] = "best_match"
    # The walkway width the layout aims for; 60 cm is always the hard minimum.
    walkway_m: float = Field(0.75, ge=WALKWAY_MIN_M)
    # How the room was measured. None reads it from the twin's dimension sources.
    confidence: Confidence | None = None
    relaxations: list[
        Literal[
            "drop_optional_items",
            "smaller_products",
            "switch_archetype",
            "reduce_walkway",
            "reduce_program",
        ]
    ] = Field(default_factory=list)


class ViolationOut(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    rule: str
    item_ids: list[str]
    detail: str


class ItemFitOut(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    status: Literal["fits", "tight", "does_not_fit"]
    spare_m: float


class PlacementResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    design: Design | None
    placed_slots: list[str]
    # Optional slots that had a product but no place that passed the hard rules.
    dropped_slots: list[str]
    # Required slots with no place at all, when the design failed.
    unplaced_required: list[str]
    # Violations of the best layout the verifier rejected, when none passed.
    violations: list[ViolationOut]
    budget_ok: bool = True
    stock_ok: bool = True
    layouts_verified: int
    # Whether the room's level allows fit claims (taped or AR-measured).
    fit_claims: bool = False
    # Per floor item, only when fit claims are allowed: the verifier's fit.
    item_fits: dict[str, ItemFitOut] = Field(default_factory=dict)


@dataclass(frozen=True)
class Piece:
    slot: str
    product: Product
    cat: Category
    rect: Rect
    height: float
    wall_id: str | None
    target: str | None

    @property
    def poly(self) -> Poly:
        return self.rect.corners()

    @property
    def mount(self) -> str:
        return self.cat.mount


@dataclass(frozen=True)
class State:
    pieces: tuple[Piece, ...]
    score: float
    dropped: tuple[str, ...]
    notes: tuple[tuple[str, float], ...]

    def get(self, slot: str) -> Piece | None:
        return next((p for p in self.pieces if p.slot == slot), None)


class Solver:
    def __init__(self, room: Room, archetype: A.Archetype, walkway_m: float) -> None:
        self.room = room
        self.arch = archetype
        self.walkway = walkway_m
        self.kept_floor = [o.footprint.corners() for o in room.obstacles if o.mount == "floor"]
        self.kept_rugs = [o.footprint.corners() for o in room.obstacles if o.mount == "rug"]
        self.swings = [d.swing for d in room.doors if d.swing is not None]
        self.approaches = [d.approach.corners() for d in room.doors]
        # The required slot the search could not place, if it stopped early.
        self.stuck_at: str | None = None

    # Candidate poses.

    def _against(self, w: WallLine, width: float, depth: float, s: float) -> Rect:
        off = w.margin_m + depth / 2.0 + SNUG_M
        x, y = w.at(s)
        return Rect(
            round(x + w.inward[0] * off, 3),
            round(y + w.inward[1] * off, 3),
            width,
            depth,
            w.facing_deg,
        )

    def _walls_for(self, pick: A.WallPick, state: State) -> list[WallLine]:
        target = state.get(pick.target) if pick.target else None
        tw = self.room.wall_by_id.get(target.wall_id) if target and target.wall_id else None
        out = []
        for w in self.room.walls:
            has_window = any(o.wall_id == w.id for o in self.room.windows)
            if pick.only == "window" and not has_window:
                continue
            if pick.only == "no_window" and has_window:
                continue
            if pick.only in ("opposite", "beside", "other"):
                if tw is None:
                    # The target sits off the walls (or was dropped): fall back to its facing.
                    if target is None:
                        continue
                    dot = -(w.inward[0] * target.rect.front[0] + w.inward[1] * target.rect.front[1])
                else:
                    if w.id == tw.id:
                        continue
                    dot = w.inward[0] * tw.inward[0] + w.inward[1] * tw.inward[1]
                if pick.only == "opposite" and dot > -0.9:
                    continue
                if pick.only == "beside" and abs(dot) > 0.1:
                    continue
            out.append(w)
        return out

    def _wall_pref(self, pick: A.WallPick, w: WallLine) -> float:
        lengths = [x.length for x in self.room.walls]
        span = (max(lengths) - min(lengths)) or 1.0
        if pick.prefer == "long":
            return (w.length - min(lengths)) / span
        if pick.prefer == "short":
            return (max(lengths) - w.length) / span
        return 0.0

    def _steps(self, lo: float, hi: float) -> list[float]:
        if hi < lo:
            return []
        n = int((hi - lo) / STEP_M)
        values = {round(lo, 3), round(hi, 3), round((lo + hi) / 2.0, 3)}
        values.update(round(lo + i * STEP_M, 3) for i in range(n + 1))
        return sorted(values)

    def candidates(
        self, slot: A.Slot, product: Product, state: State
    ) -> Iterable[tuple[Rect, str | None, float]]:
        """(footprint, wall id, rule score) for every pose the rule allows."""
        dims = product.dimensions
        width, depth = high(dims.width), high(dims.depth)
        rule = slot.rule
        if isinstance(rule, A.AgainstWall):
            for w in self._walls_for(rule.walls, state):
                pref = self._wall_pref(rule.walls, w)
                target = state.get(rule.walls.target) if rule.walls.target else None
                for s in self._steps(width / 2.0, w.length - width / 2.0):
                    rect = self._against(w, width, depth, s)
                    if rule.centered:
                        shape = -abs(s - w.length / 2.0) / max(w.length, 1.0)
                    else:
                        shape = -min(s - width / 2.0, w.length - width / 2.0 - s) / max(
                            w.length, 1.0
                        )
                    if target is not None and rule.walls.only == "opposite":
                        # Square on to the target across the room.
                        lateral = abs(
                            (rect.cx - target.rect.cx) * target.rect.axis_x[0]
                            + (rect.cy - target.rect.cy) * target.rect.axis_x[1]
                        )
                        shape = -lateral
                    yield rect, w.id, pref + shape
        elif isinstance(rule, A.InCorner):
            for w in self._walls_for(rule.walls, state):
                pref = self._wall_pref(rule.walls, w)
                for s in (width / 2.0, w.length - width / 2.0):
                    for nudge in (0.0, 0.05, 0.10, 0.15, 0.20):
                        ss = s + nudge if s < w.length / 2 else s - nudge
                        yield self._against(w, width, depth, ss), w.id, pref - nudge
        elif isinstance(rule, A.InFront):
            target = state.get(rule.target)
            if target is None:
                return
            for gap in self._gaps(rule.gap_m):
                off = target.rect.depth / 2.0 + gap + depth / 2.0
                fx, fy = target.rect.front
                yield (
                    Rect(
                        round(target.rect.cx + fx * off, 3),
                        round(target.rect.cy + fy * off, 3),
                        width,
                        depth,
                        target.rect.rotation_deg,
                    ),
                    None,
                    -abs(gap - sum(rule.gap_m) / 2.0),
                )
        elif isinstance(rule, A.Facing):
            target = state.get(rule.target)
            if target is None:
                return
            for dist in self._gaps(rule.distance_m, step=0.2):
                off = target.rect.depth / 2.0 + dist - depth / 2.0
                fx, fy = target.rect.front
                rot = normalise_deg(target.rect.rotation_deg + 180.0)
                yield (
                    Rect(
                        round(target.rect.cx + fx * off, 3),
                        round(target.rect.cy + fy * off, 3),
                        width,
                        depth,
                        rot,
                    ),
                    None,
                    -abs(dist - sum(rule.distance_m) / 2.0),
                )
        elif isinstance(rule, A.AtSide):
            target = state.get(rule.target)
            if target is None:
                return
            sides = ("left", "right") if rule.side == "either" else (rule.side,)
            for side in sides:
                sign = 1.0 if side == "right" else -1.0
                ux, uy = target.rect.axis_x
                # A chair at the side turns to face the middle of the group.
                rot = normalise_deg(target.rect.rotation_deg + (90.0 if side == "right" else -90.0))
                for gap in self._gaps(rule.gap_m):
                    off = target.rect.width / 2.0 + gap + depth / 2.0
                    for slide in (0.0, -0.15, 0.15):
                        fx, fy = target.rect.front
                        yield (
                            Rect(
                                round(target.rect.cx + sign * ux * off + fx * slide, 3),
                                round(target.rect.cy + sign * uy * off + fy * slide, 3),
                                width,
                                depth,
                                rot,
                            ),
                            None,
                            -abs(gap - sum(rule.gap_m) / 2.0) - abs(slide),
                        )
        elif isinstance(rule, A.Beside):
            target = state.get(rule.target)
            if target is None:
                return
            sides = ("left", "right") if rule.side == "either" else (rule.side,)
            for side in sides:
                sign = 1.0 if side == "right" else -1.0
                ux, uy = target.rect.axis_x
                fx, fy = target.rect.front
                back = -target.rect.depth / 2.0 + depth / 2.0
                for gap in self._gaps(rule.gap_m, step=0.04):
                    off = target.rect.width / 2.0 + gap + width / 2.0
                    yield (
                        Rect(
                            round(target.rect.cx + sign * ux * off + fx * back, 3),
                            round(target.rect.cy + sign * uy * off + fy * back, 3),
                            width,
                            depth,
                            target.rect.rotation_deg,
                        ),
                        target.wall_id,
                        -gap,
                    )
        elif isinstance(rule, A.Corner):
            near = state.get(rule.near) if rule.near else None
            for rect, wid in self._corner_poses(width, depth):
                score = -math.dist(rect.center, near.rect.center) if near else 0.0
                yield rect, wid, score
        elif isinstance(rule, A.Under):
            target = state.get(rule.target)
            if target is None:
                return
            fx, fy = target.rect.front
            # The rug's back edge runs under the target's front by the tuck.
            for tuck in (rule.tuck_m, rule.tuck_m + 0.1, max(0.0, rule.tuck_m - 0.1)):
                for turn in (0.0, 90.0):
                    # A turned rug keeps its catalog width and depth; only the rotation changes.
                    along = depth if turn == 0 else width
                    off = target.rect.depth / 2.0 - tuck + along / 2.0
                    yield (
                        Rect(
                            round(target.rect.cx + fx * off, 3),
                            round(target.rect.cy + fy * off, 3),
                            width,
                            depth,
                            normalise_deg(target.rect.rotation_deg + turn),
                        ),
                        None,
                        -abs(tuck - rule.tuck_m) - (0.05 if turn else 0.0),
                    )
        elif isinstance(rule, A.OnWallAbove):
            target = state.get(rule.target)
            if target is None or target.wall_id is None:
                return
            w = self.room.wall_by_id[target.wall_id]
            dx, dy = w.direction
            s = (target.rect.cx - w.a[0]) * dx + (target.rect.cy - w.a[1]) * dy
            x, y = w.at(s)
            off = depth / 2.0
            yield (
                Rect(
                    round(x + w.inward[0] * off, 3),
                    round(y + w.inward[1] * off, 3),
                    width,
                    depth,
                    w.facing_deg,
                ),
                w.id,
                0.0,
            )
        elif isinstance(rule, A.Ceiling):
            target = state.get(rule.target) if rule.target else None
            if target is not None:
                yield (
                    Rect(target.rect.cx, target.rect.cy, width, depth, target.rect.rotation_deg),
                    None,
                    0.0,
                )
            xs = [p[0] for p in self.room.floor]
            ys = [p[1] for p in self.room.floor]
            yield (
                Rect(
                    round((min(xs) + max(xs)) / 2, 3),
                    round((min(ys) + max(ys)) / 2, 3),
                    width,
                    depth,
                    0.0,
                ),
                None,
                -0.1,
            )
        elif isinstance(rule, A.OnTop):
            target = state.get(rule.target)
            if target is not None:
                yield (
                    Rect(target.rect.cx, target.rect.cy, width, depth, target.rect.rotation_deg),
                    None,
                    0.0,
                )

    def _gaps(self, span: tuple[float, float], step: float = 0.05) -> list[float]:
        lo, hi = span
        n = max(1, round((hi - lo) / step))
        return sorted(
            {round(lo + (hi - lo) * i / n, 3) for i in range(n + 1)},
            key=lambda g: (abs(g - (lo + hi) / 2), g),
        )

    def _corner_poses(self, width: float, depth: float) -> list[tuple[Rect, str | None]]:
        out: list[tuple[Rect, str | None]] = []
        walls = self.room.walls
        for w in walls:
            for at_start in (True, False):
                end = w.a if at_start else w.b
                other = next(
                    (
                        o
                        for o in walls
                        if o.id != w.id and min(math.dist(end, o.a), math.dist(end, o.b)) <= 0.05
                    ),
                    None,
                )
                if other is None:
                    continue
                margin = other.margin_m + SNUG_M
                s = margin + width / 2.0 if at_start else w.length - margin - width / 2.0
                rect = self._against(w, width, depth, s)
                out.append((rect, w.id))
        return out

    # Local hard checks: cheap, conservative stand-ins for the verifier's rules.

    def fits(self, piece: Piece, state: State) -> bool:
        room = self.room
        poly = piece.poly
        mount = piece.mount
        if room.in_view is not None and not point_in_polygon(piece.rect.center, room.in_view):
            return False
        if mount in ("ceiling", "surface"):
            inside = point_in_polygon(piece.rect.center, room.floor)
            return inside and (room.redo is None or point_in_polygon(piece.rect.center, room.redo))
        if mount == "wall":
            return self._wall_fits(piece)
        if not polygon_inside(poly, room.floor):
            return False
        if room.redo is not None and not polygon_inside(poly, room.redo):
            return False
        if any(wall_gap(poly, w) < w.margin_m for w in room.walls):
            return False
        if any(wall_gap(poly, e) < e.margin_m for e in room.open_edges):
            return False
        if any(overlaps(poly, s) for s in self.swings):
            return False
        if mount == "rug":
            others = [p.poly for p in state.pieces if p.mount == "rug"] + self.kept_rugs
            return not any(overlaps(poly, o) for o in others)
        if any(overlaps(poly, a) for a in self.approaches):
            return False
        for win in room.windows:
            if piece.height > win.clear_above_m and overlaps(poly, win.approach.corners()):
                return False
        for fx in room.fixtures:
            if piece.height > fx.clear_above_m and overlaps(poly, fx.zone.corners()):
                return False
        floor_others = [p for p in state.pieces if p.mount == "floor"]
        if any(overlaps(poly, p.poly) for p in floor_others) or any(
            overlaps(poly, k) for k in self.kept_floor
        ):
            return False
        mine = self._front_strip(piece)
        if mine is not None:
            if not polygon_inside(mine, room.floor):
                return False
            if any(overlaps(mine, p.poly) for p in floor_others) or any(
                overlaps(mine, k) for k in self.kept_floor
            ):
                return False
        for p in floor_others:
            theirs = self._front_strip(p)
            if theirs is not None and overlaps(theirs, poly):
                return False
        return True

    def _front_strip(self, piece: Piece) -> Poly | None:
        depth = max(
            piece.cat.opening_clearance_m, SEAT_FRONT_CLEARANCE_M if piece.cat.seating else 0.0
        )
        return piece.rect.strip("front", depth).corners() if depth > 0 else None

    def _wall_fits(self, piece: Piece) -> bool:
        c = piece.rect.center
        half = piece.rect.width / 2.0
        for w in self.room.walls:
            if w.id != piece.wall_id:
                continue
            from sajao_engine.geometry import point_segment_distance

            if point_segment_distance(c, w.a, w.b) > WALL_ITEM_REACH_M:
                return False
            dx, dy = w.direction
            s = (c[0] - w.a[0]) * dx + (c[1] - w.a[1]) * dy
            if s - half < 0 or s + half > w.length:
                return False
            for o in self.room.openings:
                if o.wall_id != w.id or (o.kind == "window" and piece.cat.key == "curtains"):
                    continue
                if s + half > o.s0 and s - half < o.s1:
                    return False
            return True
        return False

    # Soft score: how good the partial layout looks, from geometry only.

    def out_of_view_penalty(self, piece: Piece) -> float:
        """On a photo room, the share of a floor piece the photo does not show: a pose
        seen whole leaves room in view for what goes around it."""
        view = self.room.in_view
        if view is None or piece.mount != "floor":
            return 0.0
        area = polygon_area(piece.poly)
        if area <= 0:
            return 0.0
        seen = clip_convex(list(piece.poly), list(view))
        shown = polygon_area(seen) if len(seen) >= 3 else 0.0
        return OUT_OF_VIEW_WEIGHT * (1.0 - min(1.0, shown / area))

    def dead_gap_penalty(self, piece: Piece, state: State) -> float:
        """Gaps a person cannot use: wider than a hairline, narrower than a walkway."""
        if piece.mount != "floor":
            return 0.0
        penalty = 0.0
        poly = piece.poly
        for p in state.pieces:
            if p.mount != "floor" or p.slot in (piece.target,) or p.target == piece.slot:
                continue
            gap = polygon_distance(poly, p.poly)
            if 0.03 < gap < self.walkway:
                penalty += self.walkway - gap
        for k in self.kept_floor:
            gap = polygon_distance(poly, k)
            if 0.03 < gap < self.walkway:
                penalty += self.walkway - gap
        for w in self.room.walls:
            gap = wall_gap(poly, w) - w.margin_m
            if 0.03 < gap < self.walkway and piece.cat.key not in ("coffee_table", "rug"):
                penalty += (self.walkway - gap) * 0.5
        return penalty

    def _walkable(self, states: Sequence[State], slot: str) -> list[State]:
        """The best states (up to BEAM) whose walkways still pass, checked coarsely."""
        out: list[State] = []
        for st in states:
            last = st.get(slot)
            big = (
                last is not None
                and last.mount == "floor"
                and last.rect.width * last.rect.depth >= LARGE_M2
            )
            if not big or self.walk_ok(st):
                out.append(st)
            if len(out) >= BEAM:
                break
        return out

    def walk_ok(self, state: State) -> bool:
        floor = [p for p in state.pieces if p.mount == "floor"]
        footprints = [p.poly for p in floor] + self.kept_floor
        targets = [
            AccessTarget(
                p.slot,
                tuple(p.rect.strip(side, 0.10).corners() for side in p.cat.access),
                p.cat.any_side,
            )
            for p in floor
            if p.cat.access
        ]
        return check_walkways(
            self.room, footprints, targets, WALKWAY_MIN_M, cell=SEARCH_CELL_M
        ).passed

    def solve(self, choices: dict[str, Product]) -> list[State]:
        states = [State((), 0.0, (), ())]
        for slot in self.arch.slots:
            product = choices.get(slot.key)
            if product is None:
                continue
            cat = category(product.category)
            if cat.key not in slot.categories and product.category not in slot.categories:
                continue
            nxt: list[State] = []
            for state in states:
                options: list[tuple[float, Piece]] = []
                for rect, wall_id, rule_score in self.candidates(slot, product, state):
                    target = _rule_target(slot.rule)
                    piece = Piece(
                        slot.key,
                        product,
                        cat,
                        rect,
                        high(product.dimensions.height),
                        wall_id,
                        target,
                    )
                    if not self.fits(piece, state):
                        continue
                    score = _bounded(
                        rule_score
                        - self.dead_gap_penalty(piece, state)
                        - self.out_of_view_penalty(piece)
                    )
                    options.append((score, piece))
                options.sort(
                    key=lambda o: (-o[0], o[1].rect.cx, o[1].rect.cy, o[1].rect.rotation_deg)
                )
                for score, piece in _diverse(options):
                    nxt.append(
                        State(
                            (*state.pieces, piece),
                            state.score + score,
                            state.dropped,
                            (*state.notes, (slot.key, score)),
                        )
                    )
                if not slot.required:
                    # Leaving an optional item out is always a way on; it ranks below placing it,
                    # and it is what remains when every placement would cut a walkway.
                    nxt.append(
                        replace(
                            state,
                            dropped=(*state.dropped, slot.key),
                            score=state.score - DROP_PENALTY,
                        )
                    )
            nxt.sort(key=lambda s: (-s.score, _state_key(s)))
            states = self._walkable(_dedupe(nxt), slot.key)
            if not states:
                self.stuck_at = slot.key
                return []
        return states


# A twin edit's label is at most this long (the contract's limit); catalog titles run longer.
LABEL_MAX = 80


def short_label(title: str, limit: int = LABEL_MAX) -> str:
    """A product title cut to the label limit at a word boundary."""
    title = " ".join(title.split())
    if len(title) <= limit:
        return title
    cut = title[: limit - 3].rsplit(" ", 1)[0].rstrip(" ,-(")
    return f"{cut}..."


def _bounded(raw: float) -> float:
    """Keep the order of scores but never let one placement score below -SLOT_FLOOR.

    Placing an optional item, however awkwardly, then always beats dropping it.
    """
    return raw if raw >= 0 else -SLOT_FLOOR * (1.0 - math.exp(raw / SLOT_FLOOR))


def _diverse(options: Sequence[tuple[float, Piece]]) -> list[tuple[float, Piece]]:
    """The best options, at most PER_WALL from any one wall, PER_STATE in all."""
    per: dict[str | None, int] = {}
    out = []
    for score, piece in options:
        key = piece.wall_id
        if key is not None and per.get(key, 0) >= PER_WALL:
            continue
        per[key] = per.get(key, 0) + 1
        out.append((score, piece))
        if len(out) >= PER_STATE:
            break
    return out


def _rule_target(rule: A.Rule) -> str | None:
    return getattr(rule, "target", None) or getattr(rule, "near", None)


def _state_key(s: State) -> tuple[tuple[str, float, float, float], ...]:
    return tuple((p.slot, p.rect.cx, p.rect.cy, p.rect.rotation_deg) for p in s.pieces)


def _dedupe(states: Sequence[State]) -> list[State]:
    seen: set[tuple[tuple[str, float, float, float], ...]] = set()
    out = []
    for s in states:
        k = _state_key(s)
        if k not in seen:
            seen.add(k)
            out.append(s)
    return out


def removed_objects(twin: SpaceTwin, brief: Brief) -> list[str]:
    """What makes way for the design. The brief's keep list wins; then each object's own
    keep or replace (set by the rule or by the person); without one, furniture, rugs and
    loose decor go."""
    keep = {k.root for k in brief.keep_item_ids}
    out = []
    for o in twin.objects:
        if o.id in keep:
            continue
        state = o.redesign.state if o.redesign is not None else None
        if state is not None:
            if state != "keep":
                out.append(o.id)
        elif (o.object_type or "furniture") in ("furniture", "textile", "decor"):
            out.append(o.id)
    return out


def _edit_id(prefix: str, key: str, used: set[str]) -> str:
    base = f"{prefix}-{key}"[:36]
    candidate = base
    n = 1
    while candidate in used:
        candidate = f"{base[:33]}-{n}"
        n += 1
    used.add(candidate)
    return candidate


def _lighting(pieces: Sequence[Piece]) -> list[str]:
    keys = {p.cat.key for p in pieces}
    layers = []
    if keys & {"pendant_light", "ceiling_light"}:
        layers.append("ambient")
    if keys & {"table_lamp", "floor_lamp"}:
        layers.append("task")
    if keys & {"wall_light", "art"}:
        layers.append("accent")
    # The room's own ceiling light stays when the design adds none.
    return layers or ["ambient"]


def _explanations(state: State, room: Room, verification: Verification) -> list[str]:
    """Why this works, from the solver's and verifier's own numbers."""
    out: list[str] = []
    seat = next(
        (
            p
            for p in state.pieces
            if p.cat.seating and p.cat.key not in ("armchair", "accent_chair", "bench")
        ),
        None,
    )
    tv = state.get("tv_unit")
    if seat is not None and tv is not None:
        dist = polygon_distance(seat.poly, tv.poly)
        out.append(
            f"The TV unit is {dist:.1f} m from the {seat.cat.key.replace('_', ' ')}, square on."
        )
    table = state.get("coffee_table")
    if seat is not None and table is not None:
        if verification.fit_claims:
            gap = polygon_distance(seat.poly, table.poly)
            out.append(
                f"The coffee table sits {gap * 100:.0f} cm in front of the seat, within easy reach."
            )
        else:
            # Gaps are shown only for measured rooms.
            out.append("The coffee table sits in front of the seat, within easy reach.")
    bed = state.get("bed")
    if bed is not None:
        stands = [p for p in state.pieces if p.cat.key == "nightstand"]
        if len(stands) == 2:
            out.append("The bed is centered with a nightstand on each side.")
    pref = next((r for r in verification.report.rules if r.rule == "walkway_preferred"), None)
    width = 75 if pref is not None and pref.passed else 60
    if verification.fit_claims:
        out.append(f"Walkways are at least {width} cm wide from the door to everything you use.")
        fits = verification.item_fits.values()
        if fits and all(f.status == "fits" for f in fits):
            spare = min(f.spare_m for f in fits)
            out.append(f"Every piece fits with at least {spare * 100:.0f} cm to spare.")
    else:
        # Estimated sizes: checked with the scan's error band as margin, but no fit is claimed.
        out.append(
            f"Planned for walkways of at least {width} cm with the scan's error band as margin; "
            "measure the room to confirm the fit."
        )
    if any(p.cat.key == "rug" for p in state.pieces) and seat is not None:
        out.append("The rug runs under the front of the seating to tie the group together.")
    return out


def build_design(req: PlacementRequest, state: State, room: Room, removed: Sequence[str]) -> Design:
    """The Design for a layout; its check report comes from the verifier."""
    used: set[str] = set()
    edits: list[dict[str, object]] = [
        {"id": _edit_id("rm", oid, used), "op": "remove", "by": "solver", "object_id": oid}
        for oid in removed
    ]
    items = []
    by_slot = {p.slot: p for p in state.pieces}
    for p in state.pieces:
        x, y = round(p.rect.cx, 3), round(p.rect.cy, 3)
        rot = round(normalise_deg(p.rect.rotation_deg), 2) % 360.0
        items.append(
            {
                "id": p.slot,
                "product": p.product.model_dump(mode="json", exclude_unset=True),
                "position": {"x_m": x, "y_m": y},
                "rotation_deg": rot,
                "placed_by": "solver",
            }
        )
        if p.mount == "wall":
            z = WALL_ITEM_CENTER_M
        elif p.mount == "ceiling":
            z = max(0.0, room.ceiling_m - p.height)
        elif p.mount == "surface" and p.target in by_slot:
            z = by_slot[p.target].height
        else:
            z = 0.0
        edits.append(
            {
                "id": _edit_id("add", p.slot, used),
                "op": "add",
                "by": "solver",
                "product_id": str(p.product.id),
                "product_size": p.product.dimensions.model_dump(mode="json"),
                "to": {"x_m": x, "y_m": y, "z_m": round(z, 3)},
                "yaw_deg": rot,
                "label": short_label(p.product.title),
            }
        )
    relaxations = list(req.relaxations)
    if state.dropped and "drop_optional_items" not in relaxations:
        relaxations.insert(0, "drop_optional_items")
    data = {
        "schema_version": "1.0",
        "id": str(req.design_id),
        "space_profile_id": str(req.space_profile_id),
        "brief_id": str(req.brief.id),
        "created_at": req.created_at.isoformat(),
        "slot": req.intent,
        "archetype": req.archetype,
        "items": items,
        "materials": {},
        "lighting": {"layers": _lighting(state.pieces)},
        "total_cost": {
            "currency": "INR",
            "amount_minor": sum(p.product.price.amount_minor for p in state.pieces),
        },
        "relaxations": relaxations,
        "check_report": {
            "passed": False,
            "checked_at": req.created_at.isoformat(),
            "rules": [],
            "budget_ok": False,
            "stock_ok": False,
        },
        "explanations": [],
        "twin": {"twin_id": str(req.twin.id), "twin_version": req.twin.version, "edits": edits},
    }
    return Design.model_validate(data)


def place(req: PlacementRequest) -> PlacementResult:
    """Place the chosen products for one archetype. Pure and deterministic."""
    arch = A.ARCHETYPES.get(req.archetype)
    if arch is None:
        raise ValueError(f"Unknown archetype {req.archetype!r}")
    if arch.space != req.twin.space_type:
        raise ValueError(f"Archetype {arch.key} is for a {arch.space}, not a {req.twin.space_type}")
    removed = removed_objects(req.twin, req.brief)
    redo = req.redo.polygon if req.redo is not None and req.redo.scope == "part" else None
    room = room_from_twin(
        req.twin,
        removed=removed,
        redo=[(p.x_m, p.y_m) for p in redo] if redo else None,
        confidence=req.confidence,
        in_view=req.in_view,
    )
    choices = {c.slot: c.product for c in req.choices}
    solver = Solver(room, arch, req.walkway_m)
    finals = solver.solve(choices)

    required = [s.key for s in arch.slots if s.required]
    if not finals:
        return PlacementResult(
            design=None,
            placed_slots=[],
            dropped_slots=[],
            unplaced_required=[solver.stuck_at] if solver.stuck_at else required,
            violations=[],
            layouts_verified=0,
        )
    best_fail: Verification | None = None
    passing: list[tuple[float, State, Design, Verification]] = []
    tried = 0
    for state in finals[:FINALS]:
        tried += 1
        draft = build_design(req, state, room, removed)
        result = verify(
            draft,
            req.twin,
            req.brief,
            redo=req.redo,
            checked_at=req.created_at,
            confidence=req.confidence,
        )
        if result.passed:
            pref = next(
                (r.passed for r in result.report.rules if r.rule == "walkway_preferred"), False
            )
            score = state.score + (2.0 if pref or req.walkway_m <= WALKWAY_MIN_M else 0.0)
            passing.append((score, state, draft, result))
        elif best_fail is None:
            best_fail = result
    if not passing and best_fail is not None:
        return PlacementResult(
            design=None,
            placed_slots=[p.slot for p in finals[0].pieces],
            dropped_slots=list(finals[0].dropped),
            unplaced_required=[],
            violations=[
                ViolationOut(rule=v.rule, item_ids=list(v.item_ids), detail=v.detail)
                for v in best_fail.violations
            ],
            budget_ok=best_fail.report.budget_ok,
            stock_ok=best_fail.report.stock_ok,
            layouts_verified=tried,
        )
    passing.sort(key=lambda t: (-t[0], _state_key(t[1])))
    _, state, draft, result = passing[0]
    data = draft.model_dump(mode="json", exclude_unset=True)
    data["check_report"] = result.report.model_dump(mode="json", exclude_unset=True)
    data["explanations"] = _explanations(state, room, result)
    # An estimated room makes the whole design illustrative (no fit or gap claims).
    data["measurement_level"] = result.confidence
    return PlacementResult(
        design=Design.model_validate(data),
        fit_claims=result.fit_claims,
        item_fits={
            k: ItemFitOut(status=f.status, spare_m=f.spare_m) for k, f in result.item_fits.items()
        },
        placed_slots=[p.slot for p in state.pieces],
        dropped_slots=list(state.dropped),
        unplaced_required=[],
        violations=[],
        layouts_verified=tried,
    )


__all__ = ["PlacementRequest", "PlacementResult", "SlotChoice", "place"]
