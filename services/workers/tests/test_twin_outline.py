"""A mask's outline on its photo, in shares of the photo's size."""

import numpy as np
import pytest

from sajao_workers.twin.outline import MAX_POINTS, outline


def area(poly: list[dict[str, float]]) -> float:
    x = np.array([p["x"] for p in poly])
    y = np.array([p["y"] for p in poly])
    return 0.5 * abs(float(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1))))


def test_a_rectangle_is_four_corners_with_its_area() -> None:
    m = np.zeros((300, 400), bool)
    m[50:200, 100:300] = True
    (ring,) = outline(m)
    assert len(ring) == 4
    assert area(ring) == pytest.approx(m.mean(), abs=0.01)


def test_shapes_keep_their_area_and_stay_on_the_photo() -> None:
    yy, xx = np.mgrid[0:600, 0:800]
    disc = (yy - 300) ** 2 + (xx - 400) ** 2 < 200**2
    ell = np.zeros((300, 400), bool)
    ell[50:250, 50:120] = True
    ell[180:250, 50:300] = True
    for mask in (disc, ell):
        (ring,) = outline(mask)
        assert 3 <= len(ring) <= MAX_POINTS
        assert area(ring) == pytest.approx(mask.mean(), abs=0.01)
        assert all(0 <= p["x"] <= 1 and 0 <= p["y"] <= 1 for p in ring)


def test_parts_come_largest_first_and_specks_are_dropped() -> None:
    m = np.zeros((300, 400), bool)
    m[10:60, 10:60] = True
    m[100:290, 200:390] = True
    m[5:7, 300:302] = True  # a speck
    rings = outline(m)
    assert len(rings) == 2
    assert area(rings[0]) > area(rings[1])


def test_a_ragged_mask_stays_under_the_point_cap() -> None:
    rng = np.random.default_rng(0)
    yy, xx = np.mgrid[0:600, 0:800]
    radius = 200 + 25 * np.sin(np.arctan2(yy - 300, xx - 400) * 40) + rng.normal(0, 2, (600, 800))
    (ring,) = outline((yy - 300) ** 2 + (xx - 400) ** 2 < radius**2)
    assert len(ring) <= MAX_POINTS


def test_nothing_to_draw() -> None:
    assert outline(np.zeros((50, 50), bool)) == []
