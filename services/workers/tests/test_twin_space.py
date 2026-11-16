"""The space frame and the room shell, from depth points in the AR world (y up)."""

from collections.abc import Callable

import numpy as np
import pytest

from sajao_workers.twin.space import fit_space

Room = Callable[..., np.ndarray]  # the room fixture from conftest.py


def test_a_turned_room_is_measured_from_its_points(room: Room) -> None:
    space = fit_space(room(), depth_source="lidar")

    walls = sorted(w["length"]["value_m"] for w in space.shell["walls"])
    assert walls == pytest.approx([3.0, 3.0, 4.0, 4.0], abs=0.05)
    assert space.shell["ceiling_height"]["value_m"] == pytest.approx(2.7, abs=0.04)
    assert len(space.shell["floor_polygon"]) == 4
    assert space.extent == "whole_room"


def test_every_shell_length_is_an_estimated_dimension_with_a_band(
    room: Room,
) -> None:
    space = fit_space(room(), depth_source="lidar")

    for dim in [w["length"] for w in space.shell["walls"]] + [space.shell["ceiling_height"]]:
        assert dim["source"] == "estimated" and dim["error_band_m"] > 0


def test_the_space_frame_puts_the_floor_at_zero_and_z_up(room: Room) -> None:
    points = room()
    space = fit_space(points, depth_source="lidar")

    mapped = np.array([space.point(p) for p in points[:8000]])  # floor and ceiling samples
    assert np.percentile(mapped[:4000, 2], 50) == pytest.approx(0.0, abs=0.02)
    assert np.percentile(mapped[4000:8000, 2], 50) == pytest.approx(2.7, abs=0.02)
    assert mapped[:, 0].min() > -0.1 and mapped[:, 1].min() > -0.1


def test_a_room_missing_a_wall_is_a_part(room: Room) -> None:
    assert fit_space(room(skip_wall=2), depth_source="lidar").extent == "part"


def test_image_depth_gets_wider_shell_bands(room: Room) -> None:
    lidar = fit_space(room(), depth_source="lidar").shell["ceiling_height"]
    image = fit_space(room(), depth_source="image").shell["ceiling_height"]
    assert image["error_band_m"] > lidar["error_band_m"]


def test_directions_turn_with_the_room(room: Room) -> None:
    space = fit_space(room(yaw_deg=30.0), depth_source="lidar")

    # AR -Z turned into the space frame keeps a valid bearing in 0 to 360.
    bearing = space.bearing_of_ar_minus_z()
    assert 0.0 <= bearing < 360.0
    # A box yaw in the AR world maps into the space frame within a half turn.
    assert 0.0 <= space.yaw_deg(10.0) < 180.0
