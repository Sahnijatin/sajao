"""Geometry and fusion ported from the SJ-116 spike, with its tests."""

import math

import pytest

from sajao_workers.twin.fusion import Observation, fuse, instance_boxes, merge_instances, voxelize
from sajao_workers.twin.geometry import convex_hull, fit_upright_box, min_area_rect


def close(a: float, b: float, tol: float = 1e-6) -> bool:
    return abs(a - b) <= tol


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


def test_fuse_merges_overlapping_same_class_only() -> None:
    pts = [(x * 0.05, y * 0.05, 0.0) for x in range(10) for y in range(10)]
    shifted = [(x + 0.1, y, z) for x, y, z in pts]
    obs = [
        Observation(0, "chair", 0.9, voxelize(pts, 0.05), key=7),
        Observation(1, "armchair", 0.8, voxelize(shifted, 0.05), key=8),
        Observation(2, "table", 0.7, voxelize(pts, 0.05)),
    ]
    inst = fuse(obs)
    assert len(inst) == 2
    chair = next(i for i in inst if i.label == "chair")
    assert chair.frames == {0, 1}
    assert chair.members == [(0, 7), (1, 8)]


def test_instance_boxes_requires_enough_frames() -> None:
    pts = [(x * 0.05, z * 0.05, y * 0.05) for x in range(20) for y in range(10) for z in range(8)]
    vox = voxelize(pts, 0.05)
    inst = fuse([Observation(i, "sofa", 1.0, vox) for i in range(4)])
    boxes = instance_boxes(inst, up_axis=1, min_frames=3)
    assert len(boxes) == 1
    label, b, n = boxes[0]
    assert label == "sofa" and n == 4
    assert b.length == pytest.approx(0.95, abs=0.06)
    assert instance_boxes(inst, up_axis=1, min_frames=5) == []


def test_merge_instances_joins_split_object() -> None:
    left = [(x * 0.05, 0.0, 0.0) for x in range(10)]
    right = [(x * 0.05, 0.0, 0.0) for x in range(6, 16)]
    far = [(x * 0.05 + 5, 0.0, 0.0) for x in range(10)]
    inst = fuse(
        [
            Observation(0, "sofa", 1.0, voxelize(left, 0.05), key=1),
            Observation(1, "sofa", 1.0, voxelize(right, 0.05), key=2),
            Observation(2, "sofa", 1.0, voxelize(far, 0.05), key=3),
        ],
        min_overlap=0.5,
    )
    assert len(inst) == 3
    merged = merge_instances(inst, min_overlap=0.3)
    assert len(merged) == 2
    big = max(merged, key=lambda i: len(i.hits))
    assert big.frames == {0, 1}
    assert sorted(big.members) == [(0, 1), (1, 2)]


def test_fusion_groups_by_the_twin_vocabulary() -> None:
    pts = [(x * 0.05, y * 0.05, 0.0) for x in range(10) for y in range(10)]
    vox = voxelize(pts, 0.05)
    inst = fuse(
        [
            Observation(0, "wardrobe", 0.9, vox),
            Observation(1, "cabinet", 0.5, vox),
            Observation(2, "sofa", 0.9, vox),
        ]
    )
    assert sorted(i.label for i in inst) == ["sofa", "wardrobe"]
