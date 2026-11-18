"""Imported photos to a frames manifest: cameras from the pose model, metres and up from code."""

import io
import json
import math
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from PIL import Image

from sajao_gateway import (
    InMemorySpendLedger,
    InvalidOutputError,
    ModelGateway,
    ProviderResult,
    SpendCaps,
)
from sajao_workers.models import MAPANYTHING_APACHE, SPLAT_GPUS, pose_chain
from sajao_workers.steps import LocalArtifactStore, StepFailedError, StepRunner
from sajao_workers.twin.photo_frames import photo_poses_step, photo_scale_step
from sajao_workers.validate import check_poses

ROOMY = SpendCaps(per_user_daily_micro_inr=10**12, global_daily_micro_inr=10**12)
W, H = 64, 48
K = [[50.0, 0.0, 32.0], [0.0, 50.0, 24.0], [0.0, 0.0, 1.0]]
TRUE_DEPTH_M = 3.0
MODEL_SCALE = 0.5  # the pose model's world is half size
# The pose model's world is tilted 30 degrees about x against gravity.
TILT = math.radians(30)
R_TILT = np.array(
    [[1, 0, 0], [0, math.cos(TILT), -math.sin(TILT)], [0, math.sin(TILT), math.cos(TILT)]]
)


def npy(units: float) -> bytes:
    buf = io.BytesIO()
    np.save(buf, np.full((H, W), units, dtype=np.float32))
    return buf.getvalue()


def png_mm(metres: float) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(np.full((H, W), round(metres * 1000), dtype=np.uint16)).save(buf, format="PNG")
    return buf.getvalue()


def capture(store: LocalArtifactStore, n: int = 3) -> tuple[dict[str, Any], dict[str, str]]:
    keyframes = [
        {"id": f"k{i}", "image": f"u/k{i}.jpg", "captured_at_ms": 500 * i, "sharpness": 0}
        for i in range(n)
    ]
    images = {str(k["id"]): store.put_blob(f"photo {k['id']}".encode()) for k in keyframes}
    doc: dict[str, Any] = {
        "id": "00000000-0000-4000-8000-0000000000c1",
        "package": {
            "ar": {"tracking": "none", "lidar": False, "depth": False},
            "keyframes": keyframes,
            "detections": [],
            "sensor_log": "u/log.jsonl",
        },
    }
    return doc, images


def level_camera(x: float, yaw_deg: float) -> np.ndarray:
    """A level OpenCV camera in a y-up world at height 1.4, looking along -z turned by yaw."""
    yaw = math.radians(yaw_deg)
    forward = np.array([-math.sin(yaw), 0.0, -math.cos(yaw)])
    down = np.array([0.0, -1.0, 0.0])
    right = np.cross(down, forward)
    c2w = np.eye(4)
    c2w[:3, :3] = np.column_stack([right, down, forward])
    c2w[:3, 3] = [x, 1.4, 0.0]
    return c2w


TRUE = [level_camera(0.0, 0), level_camera(1.0, 40), level_camera(2.0, -30)]


def model_reply(
    store: LocalArtifactStore,
    payload: Mapping[str, Any],
    weak: tuple[int, ...] = (),
    **change: Any,
) -> dict[str, Any]:
    """What the pose model says: the true cameras in a tilted, half-size world."""
    frames = []
    for i, (f, true) in enumerate(zip(payload["frames"], TRUE, strict=False)):
        c2w = np.eye(4)
        c2w[:3, :3] = R_TILT @ true[:3, :3]
        c2w[:3, 3] = MODEL_SCALE * (R_TILT @ true[:3, 3])
        frames.append(
            {
                "image": f["image"],
                "c2w": c2w.tolist(),
                "intrinsics": K,
                "width": W,
                "height": H,
                "pose_depth": store.put_blob(npy(MODEL_SCALE * TRUE_DEPTH_M)),
                "coverage": 0.05 if i in weak else 0.9,
                **change,
            }
        )
    return {"frames": frames}


def gateway_for(
    store: LocalArtifactStore, weak: tuple[int, ...] = (), **change: Any
) -> ModelGateway:
    async def invoke(_model: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        return {"output": model_reply(store, payload, weak, **change), "gpu_seconds": 20.0}

    return ModelGateway(pose_chain(invoke), ledger=InMemorySpendLedger(ROOMY))


async def poses(store: LocalArtifactStore, gateway: ModelGateway) -> dict[str, Any]:
    doc, images = capture(store)
    result = await StepRunner(store, max_attempts=1).run(
        photo_poses_step(gateway),
        {
            "capture": store.put_blob(json.dumps(doc).encode()),
            "images": store.put_blob(json.dumps(images).encode()),
        },
        {},
    )
    manifest: dict[str, Any] = json.loads(store.read_blob(result.outputs["frames"]))
    return manifest


def test_poses_run_on_the_splat_gpus_with_the_apache_checkpoint() -> None:
    async def invoke(_model: str, _payload: Mapping[str, Any]) -> Mapping[str, Any]:
        return {}

    chain = pose_chain(invoke)
    assert [p.model for p in chain] == [MAPANYTHING_APACHE]
    assert MAPANYTHING_APACHE.startswith("facebook/map-anything-apache@")
    assert {p.max_concurrency for p in chain} == {SPLAT_GPUS}


async def test_photos_get_cameras_and_wait_for_metric_depth(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path)

    manifest = await poses(store, gateway_for(store))

    assert manifest["depth_source"] == "image"
    assert [f["keyframe_id"] for f in manifest["frames"]] == ["k0", "k1", "k2"]
    for f in manifest["frames"]:
        assert f["depth"] is None  # the depth step fills it
        assert f["intrinsics"] == K and (f["width"], f["height"]) == (W, H)
        assert len(f["c2w"]) == 4 and store.read_blob(f["pose_depth"])


async def test_metric_depth_sets_the_scale_and_the_cameras_set_up(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path)
    manifest = await poses(store, gateway_for(store))
    # What the depth step adds: metric depth for every photo.
    for f in manifest["frames"]:
        f["depth"] = store.put_blob(png_mm(TRUE_DEPTH_M))

    result = await StepRunner(store, max_attempts=1).run(
        photo_scale_step(), {"frames": store.put_blob(json.dumps(manifest).encode())}, {}
    )

    out = json.loads(store.read_blob(result.outputs["frames"]))
    assert result.meta["scale"] == pytest.approx(1 / MODEL_SCALE, rel=0.01)
    assert out["up_axis"] == 1 and out["depth_source"] == "image"
    c2ws = [np.asarray(f["c2w"]) for f in out["frames"]]
    for c in c2ws:
        assert -c[:3, 1] == pytest.approx([0.0, 1.0, 0.0], abs=1e-6)  # level: up is +y
        assert "pose_depth" not in out["frames"][0]
    # Distances between cameras are true metres again.
    assert np.linalg.norm(c2ws[1][:3, 3] - c2ws[0][:3, 3]) == pytest.approx(1.0, rel=0.01)
    assert np.linalg.norm(c2ws[2][:3, 3] - c2ws[0][:3, 3]) == pytest.approx(2.0, rel=0.01)


@pytest.mark.parametrize(
    "change",
    [
        {"c2w": [[2.0, 0, 0, 0], [0, 1.0, 0, 0], [0, 0, 1.0, 0], [0, 0, 0, 1.0]]},  # not a rotation
        {"c2w": [[1.0, 0, 0, float("nan")], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]},
        {"intrinsics": [[-50.0, 0, 32], [0, 50, 24], [0, 0, 1]]},
        {"intrinsics": [[50.0, 0, 500], [0, 50, 24], [0, 0, 1]]},  # centre outside the image
        {"pose_depth": "not a digest"},
        {"coverage": 0.1},  # most photos with too little depth
        {"coverage": float("nan")},
    ],
)
def test_bad_poses_are_rejected(tmp_path: Path, change: dict[str, Any]) -> None:
    store = LocalArtifactStore(tmp_path)
    payload = {"frames": [{"image": store.put_blob(b"a")}]}
    with pytest.raises(InvalidOutputError):
        check_poses(payload)(ProviderResult(model_reply(store, payload, **change)))


async def test_when_the_pose_model_fails_the_step_fails(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path)
    with pytest.raises(StepFailedError):
        await poses(store, gateway_for(store, coverage=0.0))


async def test_a_scan_with_ar_poses_is_not_for_this_step(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path)
    doc, images = capture(store)
    doc["package"]["ar"]["tracking"] = "arkit"
    with pytest.raises(StepFailedError):
        await StepRunner(store, max_attempts=1).run(
            photo_poses_step(gateway_for(store)),
            {
                "capture": store.put_blob(json.dumps(doc).encode()),
                "images": store.put_blob(json.dumps(images).encode()),
            },
            {},
        )


async def test_a_photo_with_little_depth_is_left_out_of_the_geometry(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path)
    manifest = await poses(store, gateway_for(store, weak=(1,)))
    assert [f["keyframe_id"] for f in manifest["frames"]] == ["k0", "k2"]


async def test_too_few_photos_with_depth_fail_the_step(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path)
    with pytest.raises(StepFailedError):
        await poses(store, gateway_for(store, weak=(0, 1)))
