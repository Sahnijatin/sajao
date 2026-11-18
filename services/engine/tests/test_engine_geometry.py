import math
import random

from hypothesis import given, settings
from hypothesis import strategies as st

from sajao_engine.geometry import (
    Rect,
    overlaps,
    penetration,
    point_in_polygon,
    polygon_distance,
    polygon_inside,
    sector,
)

coord = st.floats(-5, 5, allow_nan=False)
size = st.floats(0.05, 3, allow_nan=False)
angle = st.floats(0, 359.9, allow_nan=False)
rects = st.builds(Rect, coord, coord, size, size, angle)


def _sample_inside(r: Rect, rng: random.Random) -> tuple[float, float]:
    u, v = rng.uniform(-0.5, 0.5), rng.uniform(-0.5, 0.5)
    ux, uy = r.axis_x
    fx, fy = r.front
    return (r.cx + ux * u * r.width + fx * v * r.depth, r.cy + uy * u * r.width + fy * v * r.depth)


@given(rects, rects)
def test_overlap_is_symmetric(a: Rect, b: Rect) -> None:
    assert overlaps(a.corners(), b.corners()) == overlaps(b.corners(), a.corners())


@given(rects)
def test_rect_overlaps_itself(a: Rect) -> None:
    assert overlaps(a.corners(), a.corners())


@given(rects, rects)
@settings(max_examples=200)
def test_a_shared_sample_point_means_overlap(a: Rect, b: Rect) -> None:
    rng = random.Random(0)  # noqa: S311
    for _ in range(200):
        p = _sample_inside(a, rng)
        if point_in_polygon(p, b.corners()) and min(a.width, a.depth, b.width, b.depth) > 0.01:
            # A point strictly inside both, away from the edges, proves shared area.
            inner = Rect(b.cx, b.cy, b.width * 0.98, b.depth * 0.98, b.rotation_deg)
            if point_in_polygon(p, inner.corners()):
                assert penetration(a.corners(), b.corners()) > 0
                return


@given(rects, rects)
def test_apart_means_positive_distance(a: Rect, b: Rect) -> None:
    far = math.hypot(a.width, a.depth) / 2 + math.hypot(b.width, b.depth) / 2 + 0.01
    moved = Rect(a.cx + far, a.cy, b.width, b.depth, b.rotation_deg)
    assert not overlaps(a.corners(), moved.corners())
    assert polygon_distance(a.corners(), moved.corners()) > 0


@given(rects, st.floats(0, 1, allow_nan=False))
def test_grown_rect_contains_original(a: Rect, margin: float) -> None:
    assert polygon_inside(a.corners(), a.grown(margin + 1e-6).corners())


@given(rects, st.sampled_from(["front", "back", "left", "right"]), st.floats(0.01, 1))
def test_strips_touch_but_never_overlap_their_rect(a: Rect, side: str, depth: float) -> None:
    strip = a.strip(side, depth).corners()
    assert not overlaps(a.corners(), strip, eps=1e-6)
    assert polygon_distance(a.corners(), strip) < 1e-6


def test_front_faces_plus_y_at_rotation_zero() -> None:
    r = Rect(0, 0, 2, 1, 0)
    assert r.front == (math.cos(math.pi / 2), 1.0)
    front_strip = r.strip("front", 0.5)
    assert front_strip.cy > 0


def test_inside_an_l_shaped_floor() -> None:
    floor = ((0, 0), (4, 0), (4, 2), (2, 2), (2, 4), (0, 4))
    assert polygon_inside(Rect(1, 1, 1, 1).corners(), floor)
    assert polygon_inside(Rect(3, 1, 1.9, 1.9).corners(), floor)
    # Straddles the reflex corner.
    assert not polygon_inside(Rect(2.2, 2.2, 1, 1).corners(), floor)
    # Diagonal through the notch: every corner is on the floor but the middle is not.
    assert not polygon_inside(Rect(3, 3, 1.5, 1.5, 45).corners(), floor)


@given(st.floats(0.5, 1.2), st.floats(-90, 90).filter(lambda s: abs(s) > 10))
def test_sector_contains_the_true_arc(radius: float, sweep: float) -> None:
    poly = sector((0, 0), radius, 0, sweep)
    for k in range(21):
        t = math.radians(sweep * k / 20)
        p = (radius * 0.999 * math.cos(t), radius * 0.999 * math.sin(t))
        assert point_in_polygon(p, poly)
