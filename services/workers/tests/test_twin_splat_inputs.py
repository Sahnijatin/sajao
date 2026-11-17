"""Pure parts of the splat step: object labels per Gaussian, initial points, held-out views."""

import numpy as np
import pytest

from sajao_workers.twin.splat_inputs import (
    NEAR_PATH_M,
    held_out,
    held_out_split,
    initial_points,
    nearest_training_camera,
    split_views,
    summarise,
)
from sajao_workers.twin.split import BACKGROUND, assign_labels, decide_label


def test_decide_label_needs_enough_views_and_a_majority() -> None:
    assert decide_label({1: 3}, visible=4) == 1
    assert decide_label({1: 2}, visible=2) == BACKGROUND  # too few views
    assert decide_label({1: 3, 2: 4}, visible=10) == BACKGROUND  # no majority
    assert decide_label({1: 4, 2: 4}, visible=6) == 1  # tie goes to the lower id


def test_assign_labels_matches_decide_label_for_every_gaussian() -> None:
    rng = np.random.default_rng(0)
    votes = rng.integers(0, 4, size=(200, 4))
    votes[:, 0] = 0
    visible = votes.sum(1) + rng.integers(0, 5, size=200)

    labels = assign_labels(votes, visible)

    expected = [
        decide_label({k: int(v) for k, v in enumerate(row) if v}, int(vis))
        for row, vis in zip(votes, visible, strict=True)
    ]
    assert labels.tolist() == expected


def test_initial_points_unproject_depth_with_colours() -> None:
    h, w, f = 24, 32, 20.0
    k = [[f, 0.0, w / 2], [0.0, f, h / 2], [0.0, 0.0, 1.0]]
    c2w = np.eye(4).tolist()
    depth = np.full((h, w), 2.0, np.float32)
    rgb = np.zeros((h, w, 3), np.uint8)
    rgb[..., 0] = 255

    points = initial_points([(rgb, depth, k, c2w)], stride=2, max_points=10_000)

    assert points.shape == (12 * 16, 6)
    assert np.allclose(points[:, 2], 2.0)
    assert np.allclose(points[:, 3:], [1.0, 0.0, 0.0])


def test_initial_points_are_capped_and_skip_missing_depth() -> None:
    h, w = 24, 32
    k = [[20.0, 0.0, 16.0], [0.0, 20.0, 12.0], [0.0, 0.0, 1.0]]
    depth = np.zeros((h, w), np.float32)
    depth[:, :16] = 1.5
    frames = [(np.zeros((h, w, 3), np.uint8), depth, k, np.eye(4).tolist())] * 3

    points = initial_points(frames, stride=1, max_points=500)

    assert len(points) == 500
    assert np.all(points[:, 0] < 0)  # only the left half had depth


@pytest.mark.parametrize(("n", "expected"), [(20, [9, 19]), (12, [9]), (5, [])])
def test_every_tenth_frame_is_held_out(n: int, expected: list[int]) -> None:
    assert held_out(n) == expected


def walk(n: int, step_m: float) -> np.ndarray:
    """Cameras walking along x, `step_m` apart, all facing +z."""
    c2w = np.tile(np.eye(4), (n, 1, 1))
    c2w[:, 0, 3] = np.arange(n) * step_m
    return c2w


def test_the_nearest_training_camera_gives_metres_and_degrees() -> None:
    c2w = walk(3, 0.5)
    turn = np.radians(90.0)
    c2w[2, :3, :3] = [[np.cos(turn), 0, np.sin(turn)], [0, 1, 0], [-np.sin(turn), 0, np.cos(turn)]]

    (near,) = nearest_training_camera(c2w, [1], [0, 2])
    (turned,) = nearest_training_camera(c2w, [1], [2])

    assert near == pytest.approx((0.5, 0.0))
    assert turned == pytest.approx((0.5, 90.0))


def test_the_split_holds_out_a_tenth_with_views_near_and_far_from_the_path() -> None:
    c2w = walk(120, 0.2)

    test = held_out_split(c2w)
    train = [i for i in range(120) if i not in test]
    views = split_views(c2w, test, train)

    assert len(test) == 12
    assert 0 not in test and 119 not in test
    assert sum(v["split"] == "far" for v in views) == 4  # the middle of a 6-frame run
    assert sum(v["split"] == "near" for v in views) == 8
    assert all((v["nearest_m"] <= NEAR_PATH_M) == (v["split"] == "near") for v in views)
    assert held_out_split(c2w) == test  # the same room always gives the same split


def test_the_run_goes_where_it_leaves_views_farthest_from_training_cameras() -> None:
    c2w = walk(120, 0.05)  # a slow walk: no run of six is far from its neighbours...
    c2w[60:, 0, 3] = 3.0 + np.arange(60) * 0.4  # ...until the second half speeds up

    test = held_out_split(c2w)
    views = split_views(c2w, test, [i for i in range(120) if i not in test])

    far = [v["index"] for v in views if v["split"] == "far"]
    assert far and min(far) >= 60


def test_a_short_capture_falls_back_to_every_tenth_frame() -> None:
    assert held_out_split(walk(12, 0.2)) == held_out(12)


def test_scores_are_averaged_per_side_of_the_split() -> None:
    views = [
        {"split": "near", "psnr": 26.0, "ssim": 0.9, "lpips": 0.1},
        {"split": "near", "psnr": 24.0, "ssim": 0.8, "lpips": 0.2},
        {"split": "far", "psnr": 18.0, "ssim": 0.6, "lpips": 0.5},
    ]

    summary = summarise(views)

    assert summary["near"] == {"views": 2, "psnr": 25.0, "ssim": 0.85, "lpips": 0.15}
    assert summary["far"] == {"views": 1, "psnr": 18.0, "ssim": 0.6, "lpips": 0.5}
    assert summary["all"]["views"] == 3
    assert summarise(views[:2])["far"] == {"views": 0}
