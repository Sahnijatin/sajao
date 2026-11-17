"""Walkways: can a person get from the door to everything they need to reach?

Standing positions are sampled on a square grid of cell centers. The clearance
of a position is its exact distance to the nearest wall (less the wall's band)
or footprint (already grown by its band). A person of walkway width ``w`` can
stand where the clearance is at least ``w / 2``; positions joined through
neighbouring cells are a walkway. Sampling can only miss a corridor that is
within a fraction of a cell of the minimum, never invent one.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache

import numpy as np
from numpy.typing import NDArray

from sajao_engine.geometry import Poly, ccw
from sajao_engine.room import Room

CELL_M = 0.025
# A person standing in a walkway can reach a seat, a bed side or a drawer this far away.
REACH_M = 0.45

F64 = NDArray[np.float64]
Mask = NDArray[np.bool_]


@dataclass(frozen=True)
class Grid:
    x0: float
    y0: float
    cell: float
    nx: int
    ny: int

    def centers(self) -> tuple[F64, F64]:
        xs = self.x0 + (np.arange(self.nx) + 0.5) * self.cell
        ys = self.y0 + (np.arange(self.ny) + 0.5) * self.cell
        gx, gy = np.meshgrid(xs, ys)
        return gx.ravel(), gy.ravel()


def _segment_distance(px: F64, py: F64, a: tuple[float, float], b: tuple[float, float]) -> F64:
    ax, ay = a
    dx, dy = b[0] - ax, b[1] - ay
    length2 = dx * dx + dy * dy
    if length2 <= 1e-18:
        return np.asarray(np.hypot(px - ax, py - ay), dtype=np.float64)
    t = np.clip(((px - ax) * dx + (py - ay) * dy) / length2, 0.0, 1.0)
    return np.asarray(np.hypot(px - (ax + t * dx), py - (ay + t * dy)), dtype=np.float64)


def _inside(px: F64, py: F64, poly: Sequence[tuple[float, float]]) -> Mask:
    """Even-odd rule, vectorised."""
    inside = np.zeros(px.shape, dtype=bool)
    n = len(poly)
    for i in range(n):
        ax, ay = poly[i]
        bx, by = poly[(i + 1) % n]
        if ay == by:
            continue
        crosses = (ay > py) != (by > py)
        xi = ax + (py - ay) * (bx - ax) / (by - ay)
        inside ^= crosses & (xi > px)
    return inside


def polygon_distance_field(px: F64, py: F64, poly: Poly) -> F64:
    """Distance from each point to a convex polygon; 0 inside."""
    pts = ccw(poly)
    n = len(pts)
    dist = np.full(px.shape, np.inf)
    inside = np.ones(px.shape, dtype=bool)
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        dist = np.minimum(dist, _segment_distance(px, py, a, b))
        inside &= (b[0] - a[0]) * (py - a[1]) - (b[1] - a[1]) * (px - a[0]) >= 0
    return np.where(inside, 0.0, dist)


@lru_cache(maxsize=64)
def _room_field(room: Room, cell: float) -> tuple[Grid, F64, F64, F64]:
    """The grid, its centers, and each center's gap to the walls less their bands (0 outside)."""
    xs = [p[0] for p in room.floor]
    ys = [p[1] for p in room.floor]
    grid = Grid(
        min(xs) - cell,
        min(ys) - cell,
        cell,
        int((max(xs) - min(xs)) / cell) + 3,
        int((max(ys) - min(ys)) / cell) + 3,
    )
    px, py = grid.centers()
    # Only walls limit a walkway. An open edge is passable: the floor runs on into the next area.
    gap = np.full(px.shape, np.inf)
    for w in room.walls:
        gap = np.minimum(gap, _segment_distance(px, py, w.a, w.b) - w.margin_m)
    gap = np.where(_inside(px, py, room.floor), np.maximum(gap, 0.0), 0.0)
    return grid, px, py, gap


@dataclass(frozen=True)
class Clearance:
    grid: Grid
    px: F64
    py: F64
    # Exact gap from each cell center to the nearest wall or footprint, in metres; 0 if covered.
    gap: F64


def clearance(room: Room, footprints: Sequence[Poly], cell: float = CELL_M) -> Clearance:
    """Clearance of every cell center; ``footprints`` are already grown by their bands."""
    grid, px, py, wall_gap = _room_field(room, cell)
    gap = wall_gap.copy()
    for poly in footprints:
        gap = np.minimum(gap, polygon_distance_field(px, py, poly))
    return Clearance(grid, px, py, gap)


def _components(c: Clearance, width: float) -> NDArray[np.int64]:
    """Label connected standing cells (8-neighbour) for a walkway of ``width``; -1 elsewhere."""
    nx, ny = c.grid.nx, c.grid.ny
    ok = (c.gap >= width / 2.0).tolist()
    label = [-1] * (nx * ny)
    count = 0
    for start in range(nx * ny):
        if label[start] != -1 or not ok[start]:
            continue
        label[start] = count
        queue = deque([start])
        while queue:
            k = queue.popleft()
            i, j = k % nx, k // nx
            for nj in (j - 1, j, j + 1):
                if nj < 0 or nj >= ny:
                    continue
                for ni in (i - 1, i, i + 1):
                    if 0 <= ni < nx:
                        nk = nj * nx + ni
                        if label[nk] == -1 and ok[nk]:
                            label[nk] = count
                            queue.append(nk)
        count += 1
    return np.asarray(label, dtype=np.int64)


@dataclass(frozen=True)
class AccessTarget:
    item_id: str
    # Strips beside the item a person must reach; reaching one is enough when any_side.
    strips: tuple[Poly, ...]
    any_side: bool


@dataclass(frozen=True)
class WalkwayResult:
    width_m: float
    doors_connected: bool
    unreached_doors: tuple[str, ...]
    unreached_items: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return self.doors_connected and not self.unreached_items


def check_walkways(
    room: Room,
    footprints: Sequence[Poly],
    targets: Sequence[AccessTarget],
    width: float,
    *,
    cell: float = CELL_M,
    reach: float = REACH_M,
    precomputed: Clearance | None = None,
) -> WalkwayResult:
    """Doors joined by walkways of ``width``, and every target within reach of them."""
    c = precomputed or clearance(room, footprints, cell)
    label = _components(c, width)

    # Doors and open edges wide enough to walk through are the ways in; all must be joined.
    door_labels: dict[str, set[int]] = {}
    ways_in = [(d.id, d.approach) for d in room.doors] + [
        (f"open-{i + 1}", e.approach()) for i, e in enumerate(room.open_edges) if e.passable
    ]
    for way_id, approach in ways_in:
        zone = polygon_distance_field(c.px, c.py, approach.corners()) == 0.0
        door_labels[way_id] = {int(v) for v in np.unique(label[zone & (label >= 0)])}
    unreached_doors = tuple(sorted(d for d, labels in door_labels.items() if not labels))
    main: set[int]
    if door_labels:
        sets = [s for s in door_labels.values() if s]
        common = set.intersection(*sets) if sets else set()
        doors_connected = not unreached_doors and bool(common)
        main = set().union(*sets) if sets else set()
    else:
        # A partial scan may show no way in: the largest walkway stands in for it.
        values, counts = np.unique(label[label >= 0], return_counts=True)
        main = {int(values[int(np.argmax(counts))])} if len(values) else set()
        doors_connected = True

    main_mask = np.isin(label, sorted(main)) if main else np.zeros(label.shape, dtype=bool)
    mx, my = c.px[main_mask], c.py[main_mask]

    unreached: list[str] = []
    for target in targets:
        sides = 0
        for strip in target.strips:
            in_strip = (polygon_distance_field(c.px, c.py, strip) == 0.0) & (c.gap > 0.0)
            sx, sy = c.px[in_strip], c.py[in_strip]
            if len(sx) == 0 or len(mx) == 0:
                continue
            near = (
                (mx >= sx.min() - reach)
                & (mx <= sx.max() + reach)
                & (my >= sy.min() - reach)
                & (my <= sy.max() + reach)
            )
            nx_, ny_ = mx[near], my[near]
            if len(nx_) == 0:
                continue
            # Nearest walkway position to any free part of the strip, in chunks to bound memory.
            best = np.inf
            for k in range(0, len(sx), 256):
                d = np.hypot(
                    sx[k : k + 256, None] - nx_[None, :], sy[k : k + 256, None] - ny_[None, :]
                )
                best = min(best, float(d.min()))
                if best <= reach:
                    break
            sides += int(best <= reach)
        need = 1 if target.any_side else len(target.strips)
        if sides < need:
            unreached.append(target.item_id)
    return WalkwayResult(width, doors_connected, unreached_doors, tuple(unreached))
