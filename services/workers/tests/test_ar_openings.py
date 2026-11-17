"""Doors and windows from keyframe masks cast onto the phone's measured walls."""

import math
from typing import Any

import numpy as np
import pytest

from sajao_workers.ar_measurements import measure
from sajao_workers.ar_openings import cross_check, measured_space, openings_from_keyframes
from sajao_workers.plane_fixtures import DEPTH, FLOOR_Y, HEIGHT, WIDTH, horizontal, room, vertical
from sajao_workers.twin.shell import Frame

W, H, FOCAL = 640, 480, 400.0
K = np.array([[FOCAL, 0, W / 2], [0, FOCAL, H / 2], [0, 0, 1.0]])


def camera(position: tuple[float, float, float], target: tuple[float, float, float]) -> Frame:
    """A level camera at `position` looking at `target`, both in the AR world (y up)."""
    eye, at = np.array(position), np.array(target)
    forward = (at - eye) / np.linalg.norm(at - eye)
    right = np.cross(forward, [0.0, 1.0, 0.0])
    right /= np.linalg.norm(right)
    down = np.cross(forward, right)
    c2w = np.eye(4)
    c2w[:3, 0], c2w[:3, 1], c2w[:3, 2], c2w[:3, 3] = right, down, forward, eye
    return Frame(K, c2w, W, H)


def mask_of(corners: list[tuple[float, float, float]], frame: Frame) -> np.ndarray:
    """The picture of a flat upright rectangle (world corners) as a mask: what a model returns."""
    w2c = np.linalg.inv(frame.c2w)
    pixels = []
    for corner in corners:
        cam = w2c[:3, :3] @ np.array(corner) + w2c[:3, 3]
        assert cam[2] > 0.1, "the test camera must see every corner"
        pixels.append((K[0, 0] * cam[0] / cam[2] + K[0, 2], K[1, 1] * cam[1] / cam[2] + K[1, 2]))
    ys, xs = np.mgrid[0:H, 0:W]
    inside = np.ones((H, W), dtype=bool)
    n = len(pixels)
    centre = np.mean(pixels, axis=0)
    for i in range(n):
        (x0, y0), (x1, y1) = pixels[i], pixels[(i + 1) % n]
        side = (x1 - x0) * (ys + 0.5 - y0) - (y1 - y0) * (xs + 0.5 - x0)
        inner = (x1 - x0) * (centre[1] - y0) - (y1 - y0) * (centre[0] - x0)
        inside &= side * np.sign(inner) >= 0
    return inside


def upright(x0: float, x1: float, z: float, bottom: float, top: float) -> list[Any]:
    """Corners of a rectangle on the wall along a fixed z, heights above the floor."""
    return [
        (x0, FLOOR_Y + bottom, z),
        (x1, FLOOR_Y + bottom, z),
        (x1, FLOOR_Y + top, z),
        (x0, FLOOR_Y + top, z),
    ]


def measured(*extra: dict[str, Any], classed: bool = True) -> dict[str, Any]:
    ceiling = horizontal((2, 1.5), (2, 2), FLOOR_Y + HEIGHT, kind="horizontal_down")
    return measure(room(ceiling, *extra, classed=classed))


# A window on the wall along z = DEPTH: 1.4 to 2.6 m along x, sill 0.9 m, top 2.1 m.
WINDOW = upright(1.4, 2.6, DEPTH, 0.9, 2.1)
# A door on the same wall: 3.0 to 3.9 m along x, floor to 2.05 m.
DOOR = upright(3.0, 3.9, DEPTH, 0.0, 2.05)
EYE = FLOOR_Y + 1.4


def views(target_x: float) -> list[Frame]:
    """Three keyframes of the far wall from different places in the room."""
    look = (target_x, FLOOR_Y + 1.3, DEPTH)
    return [camera((x, EYE, z), look) for x, z in ((1.6, 0.6), (2.4, 0.9), (3.0, 0.5))]


def test_a_window_seen_in_keyframes_is_measured_on_the_wall_without_classed_planes() -> None:
    """An Android scan: the planes have no classes, the keyframes supply the window."""
    room_measured = measured(classed=False)
    assert room_measured["openings"] == []

    masks = [("window", mask_of(WINDOW, frame), frame) for frame in views(2.0)]
    found = openings_from_keyframes(room_measured, masks)  # type: ignore[arg-type]

    assert len(found) == 1
    window = found[0]
    assert (window["kind"], window["source"]) == ("window", "keyframes")
    assert window["width"]["value_m"] == pytest.approx(1.2, abs=0.03)
    assert window["height"]["value_m"] == pytest.approx(1.2, abs=0.03)
    assert window["sill_height"]["value_m"] == pytest.approx(0.9, abs=0.03)
    assert window["offset"]["value_m"] == pytest.approx(1.4, abs=0.03)  # nearest corner
    wall = next(w for w in room_measured["walls"] if w["id"] == window["wall_id"])
    assert wall["length"]["value_m"] == pytest.approx(WIDTH, abs=0.001)
    assert window["width"]["source"] == "estimated" and window["width"]["error_band_m"] > 0


def test_a_door_is_measured_from_the_floor_and_from_its_nearest_corner() -> None:
    masks = [("door", mask_of(DOOR, frame), frame) for frame in views(3.4)]
    door = openings_from_keyframes(measured(classed=False), masks)[0]  # type: ignore[arg-type]
    assert door["width"]["value_m"] == pytest.approx(0.9, abs=0.03)
    assert door["height"]["value_m"] == pytest.approx(2.05, abs=0.03)
    assert door["offset"]["value_m"] == pytest.approx(WIDTH - 3.9, abs=0.03)
    assert "sill_height" not in door


def test_an_opening_seen_in_one_keyframe_only_is_not_reported() -> None:
    frame = views(2.0)[0]
    assert openings_from_keyframes(measured(), [("window", mask_of(WINDOW, frame), frame)]) == []


def test_the_size_does_not_depend_on_where_the_room_sits_in_the_ar_world() -> None:
    """The same room and cameras, moved and turned in the AR world."""
    angle, shift = math.radians(37), np.array([2.5, 0.0, -1.7])
    turn = np.array(
        [[math.cos(angle), 0, -math.sin(angle)], [0, 1, 0], [math.sin(angle), 0, math.cos(angle)]]
    )

    def move_plane(plane: dict[str, Any]) -> dict[str, Any]:
        m = np.array(plane["transform"], dtype=float).reshape(4, 4).T
        moved = np.eye(4)
        moved[:3, :3], moved[:3, 3] = turn @ m[:3, :3], turn @ m[:3, 3] + shift
        return {**plane, "transform": moved.T.reshape(-1).tolist()}

    def move_frame(frame: Frame) -> Frame:
        c2w = np.eye(4)
        c2w[:3, :3], c2w[:3, 3] = turn @ frame.c2w[:3, :3], turn @ frame.c2w[:3, 3] + shift
        return Frame(K, c2w, W, H)

    ceiling = horizontal((2, 1.5), (2, 2), FLOOR_Y + HEIGHT, kind="horizontal_down")
    doc = room(ceiling, classed=False)
    doc["planes"] = [move_plane(p) for p in doc["planes"]]
    masks = [("window", mask_of(WINDOW, f), move_frame(f)) for f in views(2.0)]
    window = openings_from_keyframes(measure(doc), masks)[0]  # type: ignore[arg-type]
    assert window["width"]["value_m"] == pytest.approx(1.2, abs=0.03)
    assert window["sill_height"]["value_m"] == pytest.approx(0.9, abs=0.03)
    assert window["offset"]["value_m"] == pytest.approx(1.4, abs=0.03)


def test_nothing_is_cast_without_a_floor_or_a_wall() -> None:
    assert measured_space(measure({"planes": []})) is None
    frame = views(2.0)[0]
    masks = [("window", mask_of(WINDOW, frame), frame)] * 3
    assert openings_from_keyframes(measure({"planes": []}), masks) == []  # type: ignore[arg-type]


def test_keyframes_are_checked_against_the_planes_the_iphone_classed() -> None:
    """ARKit classed a window a little narrower than the keyframes read it."""
    plane = vertical((2.0, DEPTH), -90, 1.15, 0.9, 2.1, "window")
    room_measured = measured(plane)
    masks = [("window", mask_of(WINDOW, f), f) for f in views(2.0)]
    masks += [("door", mask_of(DOOR, f), f) for f in views(3.4)]
    from_keyframes = openings_from_keyframes(room_measured, masks)  # type: ignore[arg-type]

    rows = cross_check(room_measured["openings"], from_keyframes)

    window = next(r for r in rows if r["kind"] == "window")
    assert window["matched"] is True
    assert window["width_difference_m"] == pytest.approx(0.05, abs=0.03)  # keyframes minus plane
    assert window["sill_height_difference_m"] == pytest.approx(0.0, abs=0.03)
    # The door was never classed by the phone: only the keyframes have it.
    door = next(r for r in rows if r["kind"] == "door")
    assert door["matched"] is False and "classed" not in door
