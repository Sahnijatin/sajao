"""The pruning rules of the room splat: unseen Gaussians and near-camera floaters."""

import numpy as np

from sajao_workers.twin.splat_clean import NEAR_CAMERA_M, floaters, free_margin, unseen


def test_a_gaussian_one_camera_saw_is_unseen_and_two_cameras_keep_it() -> None:
    assert unseen(np.array([0, 1, 2, 40])).tolist() == [True, True, False, False]


def test_the_free_space_margin_grows_with_depth() -> None:
    assert free_margin(np.array([0.5, 1.0, 4.0])).tolist() == [0.10, 0.10, 0.40]


def test_a_floater_is_near_a_camera_and_seen_through_by_several() -> None:
    gap = np.array([0.2, 0.2, 0.2, 2.0, NEAR_CAMERA_M])
    free = np.array([6, 1, 6, 6, 2])
    surface = np.array([0, 0, 5, 0, 0])

    assert floaters(gap, free, surface).tolist() == [
        True,  # in front of the lens, and six cameras measured depth far behind it
        False,  # one camera is not enough evidence
        False,  # a sofa arm the phone passed: cameras measured a surface there
        False,  # mid-room: left to depth supervision, thin furniture lives here
        True,
    ]
