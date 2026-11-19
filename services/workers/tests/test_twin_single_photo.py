"""One photo to a camera on the floor: floor plane, camera height, ceiling, door, scale check."""

import numpy as np
import pytest

from sajao_workers.twin.single_photo import (
    BAND_ONE_CUE,
    BAND_TWO_CUES,
    BAND_UNCHECKED,
    MAX_CORRECTION,
    ceiling_height,
    check_scale,
    door_height,
    level_camera,
    lift,
    to_world,
)
from sajao_workers.twin.synthetic import K, render_scene
from sajao_workers.twin.synthetic import render_room as render


@pytest.mark.parametrize("tilt", [0.0, 12.0, 28.0])
def test_the_camera_stands_on_the_floor_it_sees(tilt: float) -> None:
    depth, _ = render(1.4, tilt)
    camera = level_camera(lift(depth, K))
    assert camera is not None
    assert camera.height_m == pytest.approx(1.4, abs=0.02)
    assert camera.tilt_deg == pytest.approx(tilt, abs=0.5)
    world = to_world(lift(depth, K), camera)
    assert np.percentile(world[:, 1], 1) == pytest.approx(0.0, abs=0.02)
    if tilt < 20:  # looking further down, the ceiling is out of frame
        assert world[:, 1].max() == pytest.approx(2.8, abs=0.03)


def test_the_camera_looks_along_minus_z() -> None:
    depth, _ = render(1.3, 10.0, yaw_deg=25.0)
    camera = level_camera(lift(depth, K))
    assert camera is not None
    forward = camera.c2w[:3, :3] @ np.array([0.0, 0.0, 1.0])
    assert forward[0] == pytest.approx(0.0, abs=1e-6)
    assert forward[2] < 0
    assert np.linalg.det(camera.c2w[:3, :3]) == pytest.approx(1.0)


def test_no_floor_in_the_photo_gives_no_camera() -> None:
    depth, _ = render(1.4, -35.0)  # looking up at the ceiling
    depth[depth > 0] = 3.0  # and nothing but a flat wall at that
    assert level_camera(lift(depth, K)) is None


def test_ceiling_and_door_heights_from_depth() -> None:
    depth, door = render(1.4, 5.0)
    camera = level_camera(lift(depth, K))
    assert camera is not None
    world = to_world(lift(depth, K), camera)
    assert ceiling_height(world, camera) == pytest.approx(2.8, abs=0.03)
    assert door_height(door, depth, K, camera) == pytest.approx(2.05, abs=0.04)


def test_a_door_cut_by_the_photos_top_edge_is_not_measured() -> None:
    depth, door = render(1.4, 5.0)
    camera = level_camera(lift(depth, K))
    assert camera is not None
    door[: int(np.nonzero(door.any(axis=1))[0][0]) + 1] = False
    door[0, :] = door[1:].any(axis=0)
    assert door_height(door, depth, K, camera) is None


def test_scale_with_no_cue_stands_at_the_widest_band() -> None:
    check = check_scale(None, [])
    assert (check.factor, check.band_fraction, check.outcome) == (1.0, BAND_UNCHECKED, "unchecked")


def test_cues_in_range_confirm_the_scale() -> None:
    assert check_scale(2.9, []).band_fraction == BAND_ONE_CUE
    both = check_scale(2.9, [2.08])
    assert (both.factor, both.band_fraction, both.outcome) == (1.0, BAND_TWO_CUES, "confirmed")


def test_cues_that_agree_correct_the_scale() -> None:
    # The depth model saw the room 15% small: ceiling 2.3, door 1.75.
    check = check_scale(2.3, [1.75])
    assert check.outcome == "corrected"
    assert 2.6 <= 2.3 * check.factor <= 3.3
    assert 2.0 <= 1.75 * check.factor <= 2.2


def test_cues_that_disagree_leave_the_scale() -> None:
    check = check_scale(2.3, [2.4])  # ceiling too low, door too tall
    assert (check.factor, check.outcome) == (1.0, "conflict")
    assert check.band_fraction == BAND_UNCHECKED


@pytest.mark.parametrize("ceiling", [1.2, 6.0])
def test_a_correction_too_large_is_refused(ceiling: float) -> None:
    check = check_scale(ceiling, [])
    assert check.outcome == "implausible" and check.factor == 1.0


@pytest.mark.parametrize("ceiling", np.linspace(2.0, 4.2, 23))
def test_a_corrected_scale_stays_within_the_cap(ceiling: float) -> None:
    check = check_scale(float(ceiling), [])
    assert 1 / MAX_CORRECTION <= check.factor <= MAX_CORRECTION
    if check.outcome in ("confirmed", "corrected"):
        assert 2.6 - 1e-6 <= ceiling * check.factor <= 3.3 + 1e-6


def test_no_ceiling_in_frame_gives_no_ceiling_cue() -> None:
    depth, _ = render(1.4, 30.0)
    camera = level_camera(lift(depth, K))
    assert camera is not None
    assert ceiling_height(to_world(lift(depth, K), camera), camera) is None


def test_a_thin_strip_of_floor_is_still_the_floor() -> None:
    # A low platform covers most of the floor; the floor is 4% of the photo and the
    # platform's top, a far larger level plane, must not be taken for it.
    platform = {"x": (-2.0, 2.0), "y": (0.0, 0.5), "z": (-5.0, -1.9)}
    depth, _ = render_scene(1.4, 8.0, boxes={"platform": platform})
    camera = level_camera(lift(depth, K))
    assert camera is not None
    assert camera.height_m == pytest.approx(1.4, abs=0.04)
