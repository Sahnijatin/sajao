"""Pure parts of the splat step: object labels per Gaussian, initial points, held-out views."""

import numpy as np
import pytest

from sajao_workers.twin.splat_inputs import held_out, initial_points
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


@pytest.mark.parametrize(("n", "expected"), [(16, [7, 15]), (10, [7]), (5, [])])
def test_every_eighth_frame_is_held_out(n: int, expected: list[int]) -> None:
    assert held_out(n) == expected
