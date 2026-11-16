"""Which Gaussians an object removal takes out, and which frames get inpainted."""

import math

import numpy as np
import pytest

from sajao_workers.twin.geometry import UprightBox
from sajao_workers.twin.removal import (
    box_of,
    choose_frames,
    inside_box,
    object_index,
    removal_set,
)

# A y-up room: floor at y = 0, a wall at z = -2, a 2 x 1 x 0.8 m sofa on the floor.
SOFA = UprightBox(center=(0.0, 0.4, 0.0), length=2.0, width=1.0, height=0.8, yaw=0.0, up_axis=1)


def grid(xs: np.ndarray, ys: np.ndarray, zs: np.ndarray) -> np.ndarray:
    return np.stack(np.meshgrid(xs, ys, zs, indexing="ij"), -1).reshape(-1, 3)


def room() -> tuple[np.ndarray, np.ndarray]:
    """Gaussian centres and labels: floor, wall, the sofa (label 2), stray points."""
    floor = grid(np.linspace(-2.5, 2.5, 60), np.array([0.0]), np.linspace(-2, 2, 50))
    wall = grid(np.linspace(-2.5, 2.5, 60), np.linspace(0, 2.5, 30), np.array([-2.0]))
    sofa = grid(np.linspace(-0.9, 0.9, 12), np.linspace(0.05, 0.75, 6), np.linspace(-0.4, 0.4, 6))
    unvoted = np.array([[0.0, 0.5, 0.0], [0.5, 0.3, 0.2]])  # inside the box, no mask votes
    floater = np.array([[1.15, 0.5, 0.0]])  # just off the sofa's end, in the air
    far = np.array([[2.0, 1.0, 1.5]])  # elsewhere in the room
    means = np.concatenate([floor, wall, sofa, unvoted, floater, far])
    labels = np.zeros(len(means), np.int32)
    start = len(floor) + len(wall)
    labels[start : start + len(sofa)] = 2
    return means, labels


def test_a_point_is_inside_a_turned_box() -> None:
    box = UprightBox(
        center=(1.0, 0.5, 1.0), length=2.0, width=0.5, height=1.0, yaw=math.pi / 2, up_axis=1
    )
    # Turned 90 degrees, the 2 m side runs along z.
    points = np.array([[1.0, 0.5, 1.9], [1.9, 0.5, 1.0], [1.0, 1.2, 1.0]])
    assert inside_box(points, box, pad=0.0).tolist() == [True, False, False]
    assert inside_box(points, box, pad=0.25).tolist() == [True, False, True]


def test_the_box_comes_from_the_objects_step_output() -> None:
    dim = {"value_m": 2.0, "source": "estimated", "error_band_m": 0.5}
    obj = {
        "up_axis": 1,
        "box": {
            "center": [0.0, 0.4, 0.0],
            "yaw_deg": 90.0,
            "length": dim,
            "width": {**dim, "value_m": 1.0},
            "height": {**dim, "value_m": 0.8},
        },
    }
    box = box_of(obj)
    assert (box.length, box.width, box.height, box.up_axis) == (2.0, 1.0, 0.8, 1)
    assert math.isclose(box.yaw, math.pi / 2)


def test_removal_takes_the_object_its_unvoted_inside_and_floaters_but_not_the_shell() -> None:
    means, labels = room()
    opacity = np.ones(len(means))

    remove = removal_set(means, opacity, labels, 2, SOFA, camera_centre=np.array([0, 1.5, 2.5]))

    on_floor = means[:, 1] == 0.0
    on_wall = means[:, 2] == -2.0
    assert remove[labels == 2].all()
    assert remove[[np.flatnonzero((means == [0.0, 0.5, 0.0]).all(1))[0]]].all()
    assert remove[np.flatnonzero((means == [1.15, 0.5, 0.0]).all(1))].all()  # the floater
    assert not remove[on_floor].any()  # the floor under the sofa stays
    assert not remove[on_wall].any()
    assert not remove[np.flatnonzero((means == [2.0, 1.0, 1.5]).all(1))].any()


def test_removing_an_object_with_no_gaussians_takes_nothing_voted() -> None:
    means, labels = room()
    remove = removal_set(
        means, np.ones(len(means)), labels, 7, SOFA, camera_centre=np.array([0, 1.5, 2.5])
    )
    # Object 7 has no votes, but its box still clears what sits inside it.
    assert remove.sum() == ((labels == 2).sum() + 3)


def test_inpainting_picks_evenly_spaced_frames_that_see_the_hole() -> None:
    fractions = [0.0, 0.001, 0.05, 0.1, 0.2, 0.1, 0.05, 0.03, 0.0]

    inpaint, drop = choose_frames(fractions, max_frames=3, min_hole=0.002)

    seen = [2, 3, 4, 5, 6, 7]
    assert inpaint == [2, 4, 6]
    assert drop == [3, 5, 7]
    assert set(inpaint) | set(drop) == set(seen)


def test_every_frame_that_sees_the_hole_is_inpainted_when_there_are_few() -> None:
    assert choose_frames([0.1, 0.0, 0.2], max_frames=48, min_hole=0.002) == ([0, 2], [])


@pytest.mark.parametrize(("value", "index"), [("o1", 1), ("o12", 12)])
def test_a_twin_object_id_names_its_label(value: str, index: int) -> None:
    assert object_index(value) == index


@pytest.mark.parametrize("value", ["", "o0", "x3", "o-1", "o1.5"])
def test_a_bad_object_id_is_refused(value: str) -> None:
    with pytest.raises(ValueError, match="object id"):
        object_index(value)
