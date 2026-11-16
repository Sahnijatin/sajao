"""Doors, windows and textures of the room shell, on a synthetic room."""

from collections.abc import Callable

import numpy as np
import pytest
from PIL import Image, ImageDraw

from sajao_schemas.generated.v1 import Opening
from sajao_workers.twin.shell import (
    Frame,
    OpeningSighting,
    fuse_openings,
    sight_opening,
    surface_rectangles,
    surface_texture,
)
from sajao_workers.twin.space import Space, fit_space

W, H, F = 640, 480, 400.0
K = np.array([[F, 0, W / 2], [0, F, H / 2], [0, 0, 1.0]])


@pytest.fixture
def space(room: Callable[..., np.ndarray]) -> Space:
    return fit_space(room(), depth_source="lidar")


def camera(space: Space, at: tuple[float, float, float]) -> Frame:
    """A camera at a point of the space frame, level, looking along -y (at wall w1)."""
    right, down, forward = np.array([-1.0, 0, 0]), np.array([0, 0, -1.0]), np.array([0, -1.0, 0])
    in_space = np.column_stack([right, down, forward])
    c2w = np.eye(4)
    c2w[:3, :3] = space.rotation.T @ in_space
    c2w[:3, 3] = space.rotation.T @ (np.asarray(at) + space.origin)
    return Frame(K, c2w, W, H)


def mask_of(space: Space, frame: Frame, corners: list[tuple[float, float, float]]) -> np.ndarray:
    """The image region of a planar polygon given in the space frame."""
    world = [space.rotation.T @ (np.asarray(c) + space.origin) for c in corners]
    w2c = np.linalg.inv(frame.c2w)
    pixels = []
    for p in world:
        c = w2c[:3, :3] @ p + w2c[:3, 3]
        pixels.append((F * c[0] / c[2] + W / 2, F * c[1] / c[2] + H / 2))
    image = Image.new("L", (W, H), 0)
    ImageDraw.Draw(image).polygon(pixels, fill=255)
    return np.asarray(image) > 0


def wall_rect(
    along: tuple[float, float], z: tuple[float, float]
) -> list[tuple[float, float, float]]:
    """A rectangle on wall w1 (y = 0, x along the wall)."""
    return [
        (along[0], 0.0, z[0]),
        (along[1], 0.0, z[0]),
        (along[1], 0.0, z[1]),
        (along[0], 0.0, z[1]),
    ]


def test_a_window_seen_from_two_places_becomes_one_measured_opening(space: Space) -> None:
    w1 = space.shell["walls"][0]
    assert w1["id"] == "w1" and w1["start"] == {"x_m": 0.0, "y_m": 0.0}
    length = w1["length"]["value_m"]
    sightings = []
    for x in (length / 2 - 0.3, length / 2 + 0.3):
        frame = camera(space, (x, 2.2, 1.4))
        window = mask_of(space, frame, wall_rect((1.0, 2.2), (0.9, 2.1)))
        sighting = sight_opening("window", window, frame, space)
        assert sighting is not None and sighting.wall_id == "w1"
        sightings.append(sighting)

    (opening,) = fuse_openings(sightings, depth_source="lidar")

    Opening.model_validate(opening)
    assert opening["id"] == "win1" and opening["wall_id"] == "w1"
    assert opening["offset"]["value_m"] == pytest.approx(1.0, abs=0.05)
    assert opening["width"]["value_m"] == pytest.approx(1.2, abs=0.06)
    assert opening["sill_height"]["value_m"] == pytest.approx(0.9, abs=0.05)
    assert opening["height"]["value_m"] == pytest.approx(1.2, abs=0.06)
    assert opening["width"]["error_band_m"] >= 0.05


def test_a_door_is_measured_from_the_floor(space: Space) -> None:
    sightings = []
    for x in (1.5, 2.0):
        frame = camera(space, (x, 2.0, 1.4))
        door = mask_of(space, frame, wall_rect((2.5, 3.4), (0.0, 2.05)))
        found = sight_opening("door", door, frame, space)
        assert found is not None
        sightings.append(found)

    (opening,) = fuse_openings(sightings, depth_source="image")

    assert opening["id"] == "d1"
    assert "sill_height" not in opening
    assert opening["height"]["value_m"] == pytest.approx(2.05, abs=0.06)
    assert opening["width"]["error_band_m"] >= 0.08  # image depth: wider bands


def test_an_opening_seen_once_is_dropped_and_two_windows_stay_apart() -> None:
    sightings = [
        OpeningSighting("window", "w2", (0.5, 1.5), (0.9, 2.0)),
        OpeningSighting("window", "w2", (0.52, 1.49), (0.91, 2.0)),
        OpeningSighting("window", "w2", (2.5, 3.3), (0.9, 2.0)),
        OpeningSighting("window", "w2", (2.48, 3.31), (0.9, 2.01)),
        OpeningSighting("door", "w4", (0.2, 1.1), (0.0, 2.1)),  # seen once
    ]

    openings = fuse_openings(sightings, depth_source="lidar")

    assert [(o["id"], o["wall_id"]) for o in openings] == [("win1", "w2"), ("win2", "w2")]


def test_a_mask_that_hits_no_wall_gives_nothing(space: Space) -> None:
    frame = camera(space, (2.0, 2.0, 1.4))
    sky = np.zeros((H, W), bool)
    sky[:2, :2] = True  # too few rays
    assert sight_opening("window", sky, frame, space) is None


def test_a_wall_texture_comes_from_the_frame_that_sees_it(space: Space) -> None:
    frame = camera(space, (2.0, 2.5, 1.4))
    image = np.zeros((H, W, 3), np.uint8)
    image[:, : W // 2] = (200, 30, 30)  # image left: the +x end of wall w1
    image[:, W // 2 :] = (30, 30, 200)
    rect = surface_rectangles(space)["w1"]

    texture, seen = surface_texture(rect, [frame], [image], [None], [None], space)

    assert seen > 0.3
    middle = texture[texture.shape[0] // 2]
    assert middle[: len(middle) // 3].mean(axis=0)[2] > 150  # the start of the wall is blue
    assert middle[-len(middle) // 3 :].mean(axis=0)[0] > 150  # the end is red


def test_object_masks_keep_furniture_out_of_the_texture(space: Space) -> None:
    frame = camera(space, (2.0, 2.5, 1.4))
    image = np.full((H, W, 3), 120, np.uint8)
    blocked = np.zeros((H, W), bool)
    blocked[:, : W // 2] = True  # a sofa covers the left of the view
    rect = surface_rectangles(space)["w1"]

    _, seen_all = surface_texture(rect, [frame], [image], [None], [None], space)
    _, seen_free = surface_texture(rect, [frame], [image], [None], [blocked], space)

    assert seen_free < seen_all * 0.7
