"""Objects: lift masks with depth, fuse across frames, fit boxes with error bands."""

import io
import math

import numpy as np
import pytest
from PIL import Image

from sajao_workers.twin.fusion import Observation
from sajao_workers.twin.objects import (
    ERROR_BANDS,
    FrameMasks,
    build_objects,
    decode_depth_mm,
    decode_mask,
    dimension,
    lift_mask,
)

W, H, F = 320, 240, 250.0  # a phone frame at half resolution
K = [[F, 0.0, W / 2], [0.0, F, H / 2], [0.0, 0.0, 1.0]]


def camera_at(x: float) -> list[list[float]]:
    """OpenCV camera at height 1.2 m looking along +z, world y up (ARKit-like but y-down flip)."""
    # World is y-up; the OpenCV camera's y points down, so flip y and z.
    return [[1.0, 0.0, 0.0, x], [0.0, -1.0, 0.0, 1.2], [0.0, 0.0, -1.0, 0.0], [0, 0, 0, 1.0]]


def box_scene(cam_x: float) -> tuple[np.ndarray, np.ndarray]:
    """A 1.0 m wide, 0.8 m tall box face 3 m in front of the camera (along -z), floor at y=0.

    Returns the mask of the box and a depth image (metres) for one camera.
    """
    ys, xs = np.mgrid[0:H, 0:W]
    depth = np.full((H, W), 3.0)
    # Pixel to world on the plane z = -3: x = cam_x + (u - cx) * d / f, y = 1.2 - (v - cy) * d / f.
    wx = cam_x + (xs - W / 2) * 3.0 / F
    wy = 1.2 - (ys - H / 2) * 3.0 / F
    mask = (wx > -0.5) & (wx < 0.5) & (wy > 0.0) & (wy < 0.8)
    return mask, depth


def test_lifting_a_mask_puts_points_on_the_object() -> None:
    mask, depth = box_scene(0.0)
    points = lift_mask(mask, depth, K, camera_at(0.0), erode=0)

    assert len(points) > 50
    assert np.allclose(points[:, 2], -3.0, atol=1e-6)
    assert points[:, 0].min() > -0.56 and points[:, 0].max() < 0.56
    assert points[:, 1].min() > -0.06 and points[:, 1].max() < 0.86


def test_pixels_without_depth_are_ignored() -> None:
    mask, depth = box_scene(0.0)
    depth[:, : W // 2] = 0.0

    points = lift_mask(mask, depth, K, camera_at(0.0), erode=0)

    assert len(points) > 0
    assert points[:, 0].min() > -0.06


def test_a_mask_with_too_few_points_gives_none() -> None:
    mask = np.zeros((H, W), bool)
    mask[10:14, 10:14] = True

    assert len(lift_mask(mask, np.full((H, W), 2.0), K, camera_at(0.0))) == 0


def frames_seeing_box(label: str = "sofa", n: int = 4) -> list[FrameMasks]:
    out = []
    for i in range(n):
        x = -0.2 + 0.1 * i
        mask, depth = box_scene(x)
        out.append(FrameMasks(f"kf{i}", camera_at(x), K, depth, [(label, 0.9, mask, f"m{i}")]))
    return out


def test_objects_are_fused_across_frames_with_a_box_and_error_bands() -> None:
    objects = build_objects(frames_seeing_box(), up_axis=1, depth_source="lidar")

    assert len(objects) == 1
    sofa = objects[0]
    assert sofa["category"] == "sofa"
    assert sofa["frames"] == 4
    assert sofa["confidence"] == pytest.approx(0.9)
    assert sofa["box"]["length"]["value_m"] == pytest.approx(1.0, abs=0.12)
    assert sofa["box"]["height"]["value_m"] == pytest.approx(0.8, abs=0.12)
    assert sofa["box"]["center"][2] == pytest.approx(-3.0, abs=0.05)
    for side in ("length", "width", "height"):
        dim = sofa["box"][side]
        assert dim["source"] == "estimated"
        assert dim["error_band_m"] >= ERROR_BANDS["lidar"][0]
    assert [v["mask"] for v in sofa["views"]] == ["m0", "m1", "m2", "m3"]


def test_image_depth_gets_a_wider_band_than_lidar() -> None:
    lidar = dimension(1.0, "lidar")
    image = dimension(1.0, "image")

    assert image["error_band_m"] > lidar["error_band_m"]
    assert lidar == {"value_m": 1.0, "source": "estimated", "error_band_m": lidar["error_band_m"]}


def test_objects_seen_in_too_few_frames_are_dropped() -> None:
    assert build_objects(frames_seeing_box(n=2), up_axis=1, depth_source="lidar") == []


@pytest.mark.parametrize("scale", [0.05, 8.0])
def test_implausible_sizes_are_dropped(scale: float) -> None:
    frames = frames_seeing_box()
    shrunk = [
        FrameMasks(f.keyframe_id, f.c2w, f.intrinsics, f.depth * scale, f.masks) for f in frames
    ]
    # Scaling depth scales the lifted object: tiny or huge boxes are not furniture.
    assert build_objects(shrunk, up_axis=1, depth_source="image") == []


def test_depth_png_in_millimetres_decodes_to_metres() -> None:
    raw = (np.arange(12, dtype=np.uint16) * 250).reshape(3, 4)
    buf = io.BytesIO()
    Image.fromarray(raw).save(buf, format="PNG")

    depth = decode_depth_mm(buf.getvalue())

    assert depth.dtype == np.float32
    assert depth[2, 3] == pytest.approx(2.75)


def test_mask_png_decodes_to_bool() -> None:
    raw = np.zeros((3, 4), np.uint8)
    raw[1, 2] = 255
    buf = io.BytesIO()
    Image.fromarray(raw).save(buf, format="PNG")

    mask = decode_mask(buf.getvalue())

    assert mask.dtype == bool and mask.sum() == 1 and mask[1, 2]


def test_yaw_is_in_degrees_within_a_half_turn() -> None:
    sofa = build_objects(frames_seeing_box(), up_axis=1, depth_source="lidar")[0]
    assert 0.0 <= sofa["box"]["yaw_deg"] < 180.0
    assert math.isfinite(sofa["box"]["yaw_deg"])


def piece(
    label: str, x0: float, x1: float, z0: float, z1: float, frames: int = 4, first: int = 0
) -> list[Observation]:
    """Observations for a box piece filling x0..x1, height 0..0.8, depth z0..z1 (y up)."""
    from sajao_workers.twin.fusion import voxelize

    pts = [
        (x, y, z)
        for x in np.arange(x0, x1, 0.04)
        for y in np.arange(0.0, 0.8, 0.04)
        for z in np.arange(z0, z1, 0.04)
    ]
    return [Observation(first + i, label, 0.9, voxelize(pts, 0.05)) for i in range(frames)]


def boxes_for(*pieces: list[Observation]) -> list[tuple[str, float]]:
    from sajao_workers.twin.fusion import fuse
    from sajao_workers.twin.objects import fitted_objects

    # Each piece is fused on its own, as when views see different arms of a sofa.
    instances = [inst for p in pieces for inst in fuse(p)]
    return sorted(
        (label, round(box.length, 1)) for label, box, _, _ in fitted_objects(instances, 1)
    )


def test_touching_pieces_of_a_sofa_become_one_sofa() -> None:
    # Different views see different arms: the pieces never share a frame.
    merged = boxes_for(
        piece("sofa", 0.0, 1.0, 0.0, 0.9), piece("sofa", 1.02, 2.0, 0.0, 0.9, first=4)
    )
    assert merged == [("sofa", 2.0)]


def test_two_chairs_side_by_side_stay_two_chairs() -> None:
    chairs = boxes_for(piece("chair", 0.0, 0.5, 0.0, 0.5), piece("chair", 0.52, 1.0, 0.0, 0.5))
    assert [label for label, _ in chairs] == ["chair", "chair"]


def test_sofas_apart_stay_apart() -> None:
    sofas = boxes_for(piece("sofa", 0.0, 1.6, 0.0, 0.9), piece("sofa", 2.6, 4.2, 0.0, 0.9))
    assert len(sofas) == 2


def test_pieces_are_not_joined_past_a_plausible_size() -> None:
    long = boxes_for(piece("sofa", 0.0, 2.0, 0.0, 0.9), piece("sofa", 2.02, 4.0, 0.0, 0.9, first=4))
    assert len(long) == 2  # a 4 m sofa is two sofas, not one


def side_by_side(frames_seeing_both: int, frames_alone: int = 2) -> list[Observation]:
    """Two single sofas touching (0..0.95 and 0.97..1.9 m): `frames_seeing_both` frames
    show them as two masks; other frames each see one, overlapping the other's voxels."""
    left, right = piece("sofa", 0.0, 0.95, 0.0, 0.9, 1)[0], piece("sofa", 0.97, 1.9, 0.0, 0.9, 1)[0]
    both = piece("sofa", 0.0, 1.9, 0.0, 0.9, 1)[0]  # a view where the detector saw one box
    obs = []
    for f in range(frames_seeing_both):
        obs += [
            Observation(f, "sofa", 0.9, left.voxels, key=2 * f),
            Observation(f, "sofa", 0.9, right.voxels, key=2 * f + 1),
        ]
    for f in range(frames_seeing_both, frames_seeing_both + frames_alone):
        obs.append(Observation(f, "sofa", 0.9, both.voxels, key=100 + f))
    return obs


def objects_from(observations: list[Observation]) -> list[tuple[str, float]]:
    from sajao_workers.twin.fusion import fuse, merge_instances
    from sajao_workers.twin.objects import fitted_objects

    fitted = fitted_objects(merge_instances(fuse(observations)), 1)
    return sorted((label, round(box.length, 1)) for label, box, _, _ in fitted)


def test_sofas_seen_as_two_masks_in_several_frames_stay_two() -> None:
    assert objects_from(side_by_side(frames_seeing_both=3)) == [("sofa", 0.9), ("sofa", 0.9)]


def test_one_frame_with_two_masks_is_not_enough_to_split() -> None:
    # A single double detection is noise: one 1.9 m sofa, not two.
    assert objects_from(side_by_side(frames_seeing_both=1, frames_alone=4)) == [("sofa", 1.9)]


def test_an_observation_never_joins_an_object_already_seen_in_its_frame() -> None:
    from sajao_workers.twin.fusion import fuse

    left = piece("sofa", 0.0, 1.0, 0.0, 0.9, 1)[0]
    twice = [
        Observation(0, "sofa", 0.9, left.voxels, key=0),
        Observation(0, "sofa", 0.8, left.voxels, key=1),
    ]
    assert len(fuse(twice)) == 2


def test_fusion_counts_what_it_separated() -> None:
    from sajao_workers.twin.fusion import fuse, merge_instances

    stats: dict[str, int] = {}
    merge_instances(fuse(side_by_side(frames_seeing_both=3), stats=stats), stats=stats)
    assert stats["ambiguous_views_dropped"] == 2
