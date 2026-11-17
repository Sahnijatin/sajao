"""Hero viewpoints and the safe region: chosen by code from depth, sharpness and poses."""

import numpy as np
import pytest

from sajao_workers.twin.hero import (
    HERO_MAX,
    HERO_MIN,
    SAFE_RADIUS_M,
    FrameView,
    frame_view,
    framing,
    inside_safe_region,
    pick_hero_views,
    sharpness,
)

W, H, F = 64, 48, 40.0
K = [[F, 0.0, W / 2], [0.0, F, H / 2], [0.0, 0.0, 1.0]]


def camera(yaw_deg: float, at: tuple[float, float, float] = (0.0, 0.0, 0.0)) -> np.ndarray:
    """OpenCV camera in a z-up world: level, looking along +x when yaw is 0."""
    t = np.radians(yaw_deg)
    forward = np.array([np.cos(t), np.sin(t), 0.0])
    down = np.array([0.0, 0.0, -1.0])
    c2w = np.eye(4)
    c2w[:3, :3] = np.column_stack([np.cross(down, forward), down, forward])
    c2w[:3, 3] = at
    return c2w


def view(
    name: str,
    cells: range,
    sharp: float = 100.0,
    depth_m: float = 3.0,
    yaw_deg: float = 0.0,
    pitch_deg: float = 0.0,
    height_m: float = 1.0,
) -> FrameView:
    pose = camera(yaw_deg)
    return FrameView(
        keyframe_id=name,
        voxels=np.array(sorted(cells), dtype=np.int64),
        heights=np.full(len(cells), height_m),
        sharpness=sharp,
        median_depth_m=depth_m,
        position=pose[:3, 3],
        forward=pose[:3, 2],
        pitch_deg=pitch_deg,
    )


def test_sharpness_is_higher_for_a_detailed_image_than_a_blurred_one() -> None:
    rng = np.random.default_rng(0)
    detailed = rng.integers(0, 255, size=(48, 64)).astype(np.uint8)
    blurred = np.full((48, 64), 128, np.uint8)

    assert sharpness(detailed) > 100 * (sharpness(blurred) + 1)


def test_a_frame_view_measures_what_the_keyframe_sees() -> None:
    depth = np.full((H // 2, W // 2), 2.5, np.float32)  # depth at half the image size
    depth[:, : W // 4] = 0.0  # the left half is unknown

    seen = frame_view(
        "k1", depth, np.zeros((H, W), np.uint8), K, W, camera(0.0).tolist(), up_axis=2
    )
    turned = frame_view(
        "k2", depth, np.zeros((H, W), np.uint8), K, W, camera(180.0).tolist(), up_axis=2
    )

    assert seen.median_depth_m == pytest.approx(2.5)
    assert seen.pitch_deg == pytest.approx(0.0)
    assert seen.forward == pytest.approx([1.0, 0.0, 0.0])
    assert len(seen.heights) == len(seen.voxels)
    assert seen.heights.min() < 0 < seen.heights.max()  # cells above and below the camera
    assert len(seen.voxels) > 20
    assert not set(seen.voxels) & set(turned.voxels)  # opposite walls share no cell


def test_a_level_view_across_the_room_is_framed_better_than_a_close_up_or_a_floor_shot() -> None:
    across = view("a", range(10))
    close = view("b", range(10), depth_m=0.6)
    floor = view("c", range(10), pitch_deg=-60.0)
    down_a_little = view("d", range(10), pitch_deg=-15.0)
    up_a_little = view("e", range(10), pitch_deg=15.0)

    assert framing(across) == pytest.approx(1.0)
    assert framing(close) < 0.5 and framing(floor) < 0.5
    assert framing(down_a_little) == pytest.approx(1.0)  # shows the floor and furniture
    assert framing(up_a_little) < 1.0  # shows ceiling


def test_ceiling_earns_a_view_nothing() -> None:
    views = [view(f"k{i}", range(i * 30, i * 30 + 30), yaw_deg=i * 40) for i in range(8)]
    # Sees more cells than any other view, all of them 2.6 m above the floor.
    views.append(view("ceiling", range(1000, 1400), yaw_deg=200, height_m=3.6))

    ids = [p["keyframe_id"] for p in pick_hero_views(views)]

    assert "ceiling" not in ids and len(ids) >= 6


def test_hero_views_cover_the_room_in_as_few_views_as_possible() -> None:
    # Twelve keyframes turning through the room; each sees 40 cells, half shared with the next.
    views = [view(f"k{i}", range(i * 20, i * 20 + 40), yaw_deg=i * 30) for i in range(12)]

    picks = pick_hero_views(views)

    ids = [str(p["keyframe_id"]) for p in picks]
    assert HERO_MIN <= len(ids) <= HERO_MAX
    assert len(set(ids)) == len(ids)
    shown = set().union(*[range(int(i[1:]) * 20, int(i[1:]) * 20 + 40) for i in ids])
    assert len(shown) >= 0.9 * 260  # the six views that do not overlap come first
    assert picks[0]["coverage"] == pytest.approx(40 / 260, abs=1e-3)


def test_blurry_keyframes_and_near_duplicates_are_never_hero_views() -> None:
    views = [view(f"k{i}", range(i * 30, i * 30 + 30), yaw_deg=i * 40) for i in range(8)]
    views.append(view("blurry", range(0, 400), sharp=1.0, yaw_deg=200))  # sees the most
    views.append(view("twin-of-k0", range(0, 30), yaw_deg=2))

    ids = [p["keyframe_id"] for p in pick_hero_views(views)]

    assert "blurry" not in ids
    assert not {"k0", "twin-of-k0"} <= set(ids)


def test_a_capture_with_few_keyframes_gives_fewer_hero_views() -> None:
    views = [view(f"k{i}", range(i * 30, i * 30 + 30), yaw_deg=i * 90) for i in range(3)]

    assert 1 <= len(pick_hero_views(views)) <= 3
    assert pick_hero_views([]) == []


def test_the_same_capture_always_gives_the_same_hero_views() -> None:
    views = [view(f"k{i}", range(i * 20, i * 20 + 40), yaw_deg=i * 30) for i in range(12)]

    assert pick_hero_views(views) == pick_hero_views(list(views))


def test_the_safe_region_is_a_radius_around_the_keyframe_positions() -> None:
    anchors = np.array([[0.0, 0.0, 1.4], [1.0, 0.0, 1.4]])

    assert inside_safe_region([0.2, 0.1, 1.4], anchors)
    assert inside_safe_region([1.0, SAFE_RADIUS_M, 1.4], anchors)
    assert not inside_safe_region([0.5, 0.0, 1.4], anchors)  # between two keyframes 1 m apart
