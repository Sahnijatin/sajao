"""The photos path for phones without AR: poses from the photos, metric scale, one tape value."""

import math

import numpy as np
import pytest

from sajao_workers.twin.photos import (
    floor_up_correction,
    level_rotation,
    metric_scale,
    tape_factor,
    up_from_floor_normals,
)


def test_the_metric_scale_is_the_median_ratio_of_metric_to_model_depth() -> None:
    model = [np.full((4, 4), 2.0), np.full((4, 4), 1.0), np.zeros((4, 4))]
    metric = [np.full((4, 4), 3.0), np.full((4, 4), 1.6), np.full((4, 4), 9.0)]

    # 1.5 and 1.6 from the first two; the third has no model depth and is skipped.
    assert metric_scale(model, metric, min_pixels=4) == pytest.approx(1.55)


def test_no_usable_depth_is_an_error_not_a_guess() -> None:
    with pytest.raises(ValueError):
        metric_scale([np.zeros((4, 4))], [np.ones((4, 4))], min_pixels=4)


def opencv_c2w(yaw_deg: float, tilt_deg: float) -> np.ndarray:
    """A camera in a y-up world turned by yaw, pitched by tilt (OpenCV axes)."""
    yaw, tilt = math.radians(yaw_deg), math.radians(tilt_deg)
    forward = np.array(
        [math.sin(yaw) * math.cos(tilt), -math.sin(tilt), math.cos(yaw) * math.cos(tilt)]
    )
    up = np.array([0.0, 1.0, 0.0])
    right = np.cross(forward, up)
    right /= np.linalg.norm(right)
    down = np.cross(forward, right)
    c2w = np.eye(4)
    c2w[:3, :3] = np.column_stack([right, down, forward])
    return c2w


def test_photos_are_levelled_so_the_cameras_up_becomes_the_world_up() -> None:
    world_tilt = np.array(
        [[1, 0, 0], [0, math.cos(0.3), -math.sin(0.3)], [0, math.sin(0.3), math.cos(0.3)]]
    )
    cams = []
    for yaw in (0, 60, 120, 180, 240, 300):
        c = opencv_c2w(yaw, 5.0)  # people hold phones a little down, all round the room
        c[:3, :3] = world_tilt @ c[:3, :3]  # the pose model's world is tilted
        cams.append(c)

    r = level_rotation(cams)

    ups = [-(r @ c[:3, :3])[:, 1] for c in cams]
    mean_up = np.mean(ups, axis=0)
    assert np.degrees(np.arccos(mean_up[1] / np.linalg.norm(mean_up))) < 1.0
    assert np.allclose(r @ r.T, np.eye(3)) and np.linalg.det(r) == pytest.approx(1.0)


def walls(*lengths: float) -> list[dict[str, object]]:
    return [{"id": f"w{i}", "length": {"value_m": v, "source": "estimated", "error_band_m": 0.1}}
            for i, v in enumerate(lengths, start=1)]  # fmt: skip


def test_one_tape_value_scales_the_room_by_the_wall_it_matches_best() -> None:
    tape = [{"target": "wall_length", "value_m": 4.6}]

    factor, wall = tape_factor(walls(4.0, 3.1, 4.05, 3.0), tape)

    assert wall in ("w1", "w3")
    assert factor == pytest.approx(4.6 / 4.0, rel=0.02) or factor == pytest.approx(4.6 / 4.05)


def test_without_a_wall_tape_value_there_is_no_correction() -> None:
    assert tape_factor(walls(4.0, 3.0), [{"target": "door_height", "value_m": 2.0}]) == (1.0, None)
    assert tape_factor(walls(4.0, 3.0), []) == (1.0, None)


def test_a_tape_value_far_from_every_wall_is_refused() -> None:
    with pytest.raises(ValueError, match="matches no wall"):
        tape_factor(walls(4.0, 3.0), [{"target": "wall_length", "value_m": 9.5}])


def floor_points(tilt_deg: float, n: int = 4000, seed: int = 0) -> np.ndarray:
    """A 5 by 4 m floor at y = 0 with some furniture tops, seen in a world tilted about x."""
    rng = np.random.default_rng(seed)
    floor = np.column_stack([rng.uniform(0, 5, n), rng.normal(0, 0.005, n), rng.uniform(0, 4, n)])
    tops = np.column_stack(
        [rng.uniform(1, 2, n // 8), np.full(n // 8, 0.45), rng.uniform(1, 2, n // 8)]
    )
    walls = np.column_stack(
        [np.zeros(n // 4), rng.uniform(0, 2.7, n // 4), rng.uniform(0, 4, n // 4)]
    )
    t = math.radians(tilt_deg)
    turn = np.array([[1, 0, 0], [0, math.cos(t), -math.sin(t)], [0, math.sin(t), math.cos(t)]])
    out: np.ndarray = np.vstack([floor, tops, walls]) @ turn.T
    return out


def test_the_floor_corrects_an_up_that_the_cameras_got_a_little_wrong() -> None:
    points = floor_points(10.0)  # the cameras' up is 10 degrees off

    turn = floor_up_correction(points, np.array([0.0, 1.0, 0.0]))

    assert turn is not None
    levelled = points @ turn.T
    floor = levelled[levelled[:, 1] < np.percentile(levelled[:, 1], 30)]
    assert float(np.ptp(floor[:, 1])) < 0.1  # flat again


def test_a_floor_far_from_the_cameras_up_is_not_trusted() -> None:
    assert floor_up_correction(floor_points(40.0), np.array([0.0, 1.0, 0.0])) is None


def test_too_few_points_give_no_correction() -> None:
    assert floor_up_correction(floor_points(5.0, n=20), np.array([0.0, 1.0, 0.0])) is None


def test_floor_normals_from_single_photos_agree_on_up_despite_one_bad_photo() -> None:
    t = math.radians(8.0)
    true = np.array([0.0, math.cos(t), math.sin(t)])
    rng = np.random.default_rng(1)
    normals = [true + rng.normal(0, 0.01, 3) for _ in range(6)]
    normals.append(np.array([0.0, math.cos(0.5), math.sin(0.5)]))  # one photo's table top

    turn = up_from_floor_normals(normals, np.array([0.0, 1.0, 0.0]))

    assert turn is not None
    assert turn @ (true / np.linalg.norm(true)) == pytest.approx([0.0, 1.0, 0.0], abs=0.02)


def test_too_few_photos_with_a_floor_give_no_correction() -> None:
    assert up_from_floor_normals([np.array([0.0, 1.0, 0.0])], np.array([0.0, 1.0, 0.0])) is None
