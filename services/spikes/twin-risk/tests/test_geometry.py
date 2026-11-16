import math

import pytest

from twin_risk.geometry import (
    UprightBox,
    box_from_obb,
    convex_hull,
    fit_upright_box,
    invert_rigid,
    iou_3d,
    min_area_rect,
    parse_arkit_traj_line,
    rodrigues,
    transform_point,
)


def close(a: float, b: float, tol: float = 1e-6) -> bool:
    return abs(a - b) <= tol


def test_rodrigues_quarter_turn_about_z() -> None:
    r = rodrigues([0.0, 0.0, math.pi / 2])
    x = (r[0][0], r[1][0], r[2][0])  # image of the x axis
    assert close(x[0], 0.0) and close(x[1], 1.0) and close(x[2], 0.0)


def test_invert_rigid_round_trip() -> None:
    from twin_risk.geometry import rigid

    m = rigid(rodrigues([0.3, -0.2, 0.9]), [1.0, 2.0, -3.0])
    p = (0.4, -1.5, 2.2)
    back = transform_point(invert_rigid(m), transform_point(m, p))
    assert all(close(a, b) for a, b in zip(back, p, strict=True))


def test_traj_line_is_inverted_to_camera_to_world() -> None:
    # World-to-camera translation of (0, 0, 2) means the camera sits at z = -2.
    ts, c2w = parse_arkit_traj_line("12.5 0 0 0 0 0 2")
    assert ts == 12.5
    assert close(c2w[2][3], -2.0)
    with pytest.raises(ValueError):
        parse_arkit_traj_line("1 2 3")


def test_convex_hull_drops_interior_points() -> None:
    hull = convex_hull([(0, 0), (2, 0), (2, 2), (0, 2), (1, 1), (1, 0.5)])
    assert sorted(hull) == [(0.0, 0.0), (0.0, 2.0), (2.0, 0.0), (2.0, 2.0)]


def test_min_area_rect_recovers_rotated_rectangle() -> None:
    yaw = 0.4
    c, s = math.cos(yaw), math.sin(yaw)
    pts = []
    for u in (-1.0, -0.3, 0.5, 1.0):
        for v in (-0.25, 0.0, 0.25):
            pts.append((3 + c * u - s * v, -1 + s * u + c * v))
    cu, cv, length, width, _ang = min_area_rect(pts)
    assert close(cu, 3, 1e-6) and close(cv, -1, 1e-6)
    assert close(max(length, width), 2.0, 1e-6) and close(min(length, width), 0.5, 1e-6)


def test_fit_upright_box_y_up() -> None:
    pts = [(x / 10, y / 10, z / 10) for x in range(11) for y in range(6) for z in range(4)]
    box = fit_upright_box(pts, up_axis=1, trim=0.0)
    assert close(box.height, 0.5) and close(box.length, 1.0) and close(box.width, 0.3)
    assert close(box.center[1], 0.25)


def test_box_from_obb_swaps_axes_to_upright() -> None:
    # Box axes: column 0 is up (y), columns 1 and 2 horizontal.
    axes = [(0.0, 1.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, 1.0)]
    box = box_from_obb((1, 2, 3), axes, (0.8, 2.0, 0.5), up_axis=1)
    assert close(box.height, 0.8) and close(box.length, 2.0) and close(box.width, 0.5)
    assert close(box.yaw, 0.0)


def test_iou_identical_disjoint_and_half() -> None:
    a = UprightBox((0, 0, 0), 2, 1, 1, 0, 2)
    assert close(iou_3d(a, a), 1.0)
    far = UprightBox((10, 0, 0), 2, 1, 1, 0, 2)
    assert iou_3d(a, far) == 0.0
    shifted = UprightBox((1, 0, 0), 2, 1, 1, 0, 2)
    assert close(iou_3d(a, shifted), 1 / 3)
    rotated = UprightBox((0, 0, 0), 2, 1, 1, math.pi, 2)
    assert close(iou_3d(a, rotated), 1.0)
