"""The assembly step: shell points from depth, object crops, a validated twin stored."""

import io
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from PIL import Image

from sajao_schemas.generated.v1 import SpaceTwin
from sajao_workers.steps import LocalArtifactStore, StepFailedError, StepRunner
from sajao_workers.twin.assemble_step import assemble_step, shell_points

W, H, F = 160, 120, 100.0
K = [[F, 0.0, W / 2], [0.0, F, H / 2], [0.0, 0.0, 1.0]]


def png(array: np.ndarray) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(array).save(buf, format="PNG")
    return buf.getvalue()


# The centre of the conftest room (4 x 3 m, turned 30 degrees, floor at y = -1.2), 1.4 m up.
ROOM_CENTRE = (3.98, 0.2, -1.70)


def camera(yaw_deg: float, at: tuple[float, float, float] = (2.0, 1.4, 1.5)) -> list[list[float]]:
    """OpenCV camera in a y-up world, turned about y."""
    t = np.radians(yaw_deg)
    turn = np.array([[np.cos(t), 0, np.sin(t)], [0, 1, 0], [-np.sin(t), 0, np.cos(t)]])
    c2w = np.eye(4)
    c2w[:3, :3] = turn @ np.diag([1.0, -1.0, -1.0])  # AR camera looks along -z
    c2w[:3, 3] = at
    out: list[list[float]] = c2w.tolist()
    return out


def setup(tmp_path: Path, room: Callable[..., np.ndarray], compass: bool = True) -> tuple[Any, ...]:
    store = LocalArtifactStore(tmp_path)
    frames = []
    for i, yaw in enumerate(range(0, 360, 30)):
        frames.append(
            {
                "keyframe_id": f"k{i + 1}",
                "image": store.put_blob(png(np.full((H, W, 3), 60 + i, np.uint8))),
                "width": W,
                "height": H,
                "intrinsics": K,
                "c2w": camera(yaw, ROOM_CENTRE),
                "depth": store.put_blob(png(np.full((H // 2, W // 2), 2000, np.uint16))),
            }
        )
    mask = np.zeros((H, W), np.uint8)
    mask[40:90, 50:120] = 255
    mask_blob = store.put_blob(png(mask))
    dim = {"value_m": 1.8, "source": "estimated", "error_band_m": 0.45}
    objects = [
        {
            "category": "bed",
            "label": "Bed",
            "confidence": 0.7,
            "frames": 5,
            "up_axis": 1,
            "box": {
                "center": [2.0, 0.3, 0.5],
                "yaw_deg": 0.0,
                "length": dim,
                "width": dim,
                "height": dim,
            },
            "views": [{"keyframe_id": "k1", "mask": mask_blob}],
        }
    ]
    capture = {
        "id": "7f9c2b1e-4c1d-4f3a-9a77-1e2d3c4b5a60",
        "package": {
            "ar": {"tracking": "arkit", "lidar": True, "depth": True},
            "keyframes": [
                {
                    "id": f["keyframe_id"],
                    "image": "c/k.jpg",
                    "captured_at_ms": 100,
                    "sharpness": 1.0,
                }
                for f in frames
            ],
            "detections": [],
            "sensor_log": "c/s.jsonl",
        },
    }
    if compass:
        capture["compass"] = {"mean_heading_deg": 12.0, "sample_count": 30}
    phone = {
        "variants": {
            "500k": {"gaussians": 500_000, "bytes": 5_000_000},
            "250k": {"gaussians": 250_000, "bytes": 2_500_000},
        }
    }
    inputs = {
        "capture": store.put_blob(json.dumps(capture).encode()),
        "frames": store.put_blob(
            json.dumps({"up_axis": 1, "depth_source": "lidar", "frames": frames}).encode()
        ),
        "objects": store.put_blob(json.dumps(objects).encode()),
        "splat": store.put_blob(b"ply"),
        "phone": store.put_blob(json.dumps(phone).encode()),
        "sog_500k": store.put_blob(b"sog a"),
        "sog_250k": store.put_blob(b"sog b"),
    }
    # The depth points must describe a room for the shell fit: use the synthetic room.
    return store, inputs, room


PARAMS = {
    "twin_id": "0b7e3a4c-2f1d-4e5a-8b6c-7d8e9f0a1b2c",
    "version": 1,
    "created_at": "2026-11-16T10:00:00Z",
}


async def test_the_step_stores_a_valid_twin_with_crops(
    tmp_path: Path, room: Callable[..., np.ndarray]
) -> None:
    store, inputs, room = setup(tmp_path, room)
    step = assemble_step(points_for_shell=lambda _store, _manifest: room())

    result = await StepRunner(store, max_attempts=1).run(step, inputs, PARAMS)

    twin = json.loads(store.read_blob(result.outputs["twin"]))
    SpaceTwin.model_validate(twin)
    assert twin["space_type"] == "bedroom"
    view = twin["objects"][0]["views"][0]
    crop = store.read_blob(view["crop"].rsplit("/", 1)[-1])
    assert Image.open(io.BytesIO(crop)).size == (77, 55)  # mask box plus a 10% margin
    assert result.meta["objects"] == 1 and result.meta["extent"] in {"whole_room", "part"}
    # Every wall the level cameras see gets a texture from the keyframes, stored as an
    # artifact; a surface no frame sees (here the ceiling) gets none rather than a guess.
    coverage = result.meta["texture_coverage"]
    for surface in twin["shell"]["surfaces"]:
        if coverage[surface["id"]] > 0:
            assert surface["texture"].startswith("artifacts/blobs/")
            assert store.has_blob(surface["texture"].rsplit("/", 1)[-1])
        else:
            assert "texture" not in surface
    assert all(coverage[w["id"]] > 0.2 for w in twin["shell"]["walls"])


async def test_door_and_window_masks_become_openings_on_the_walls(
    tmp_path: Path, room: Callable[..., np.ndarray]
) -> None:
    store, inputs, room = setup(tmp_path, room)
    window = np.zeros((H, W), np.uint8)
    window[30:70, 40:110] = 255  # straight ahead, mid height: on the wall the camera faces
    blob = store.put_blob(png(window))
    # Seen twice from the first keyframe's pose (k1 and a second sighting of the same view).
    openings = [{"keyframe_id": "k1", "kind": "window", "mask": blob}] * 2
    inputs["openings"] = store.put_blob(json.dumps(openings).encode())
    step = assemble_step(points_for_shell=lambda _store, _manifest: room())

    result = await StepRunner(store, max_attempts=1).run(step, inputs, PARAMS)

    twin = json.loads(store.read_blob(result.outputs["twin"]))
    SpaceTwin.model_validate(twin)
    walls = {w["id"] for w in twin["shell"]["walls"]}
    (opening,) = twin["shell"]["openings"]
    assert opening["kind"] == "window" and opening["wall_id"] in walls
    assert opening["sill_height"]["value_m"] > 0
    assert result.meta["openings"] == ["window"]


async def test_a_capture_without_a_compass_fails_clearly(
    tmp_path: Path, room: Callable[..., np.ndarray]
) -> None:
    store, inputs, room = setup(tmp_path, room, compass=False)
    step = assemble_step(points_for_shell=lambda _store, _manifest: room())

    with pytest.raises(StepFailedError, match="compass"):
        await StepRunner(store, max_attempts=1).run(step, inputs, PARAMS)


def test_shell_points_come_from_every_frames_depth(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path)
    depth = store.put_blob(png(np.full((60, 80), 2000, np.uint16)))
    frame = {
        "keyframe_id": "k1",
        "width": 160,
        "height": 120,
        "intrinsics": K,
        "c2w": camera(0),
        "depth": depth,
    }

    points = shell_points(store, {"frames": [frame, {**frame, "keyframe_id": "k2"}]}, stride=4)

    assert points.shape == (2 * 15 * 20, 3)
    # The camera looks along world -z from z = 1.5: the wall 2 m away is at z = -0.5.
    assert np.allclose(points[:, 2], -0.5, atol=1e-6)
