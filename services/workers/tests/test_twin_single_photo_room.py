"""One photo to a twin: camera on the floor, door and ceiling scale check, open edges."""

import io
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from PIL import Image

from sajao_gateway import InMemorySpendLedger, ModelGateway, SpendCaps
from sajao_schemas.generated.v1 import SpaceTwin
from sajao_workers.models import depth_chain
from sajao_workers.steps import LocalArtifactStore, StepRunner
from sajao_workers.twin.assemble_step import assemble_step
from sajao_workers.twin.fusion import Observation, fuse, merge_instances, voxelize
from sajao_workers.twin.objects import fitted_objects
from sajao_workers.twin.single_photo import (
    BAND_ONE_CUE,
    check_scale,
    level_camera,
    lift,
    scale_object,
    to_world,
)
from sajao_workers.twin.single_photo_step import single_photo_scale_step, single_photo_step
from sajao_workers.twin.space import fit_space
from sajao_workers.twin.synthetic import H, K, W, render_room

ROOMY = SpendCaps(per_user_daily_micro_inr=10**12, global_daily_micro_inr=10**12)
PARAMS = {
    "twin_id": "0b7e3a4c-2f1d-4e5a-8b6c-7d8e9f0a1b2c",
    "version": 1,
    "created_at": "2026-11-18T10:00:00Z",
}
# The depth model sees the room 15% small: ceiling 2.38 m, door 1.74 m.
SHRINK = 0.85


def png(array: np.ndarray) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(array).save(buf, format="PNG")
    return buf.getvalue()


def jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (W, H), (190, 180, 160)).save(buf, format="JPEG")
    return buf.getvalue()


def capture_doc(heading: float | None = 40.0) -> dict[str, Any]:
    media: dict[str, Any] = {
        "id": "5b1d2c3e-4f5a-4b6c-8d7e-9f0a1b2c3d4e",
        "kind": "photo",
        "origin": "camera",
        "storage_key": "u/k0.jpg",
        "width_px": W,
        "height_px": H,
        "has_ar_pose": False,
    }
    if heading is not None:
        media["compass_heading_deg"] = heading
    return {
        "id": "7f9c2b1e-4c1d-4f3a-9a77-1e2d3c4b5a60",
        "media": [media],
        "package": {
            "ar": {"tracking": "none", "lidar": False, "depth": False},
            "keyframes": [{"id": "k0", "image": "u/k0.jpg", "captured_at_ms": 0, "sharpness": 1}],
            "detections": [],
            "sensor_log": "u/s.jsonl",
        },
    }


async def build(tmp_path: Path, heading: float | None = 40.0) -> tuple[Any, ...]:
    store = LocalArtifactStore(tmp_path)
    depth, door = render_room(1.4, 8.0)
    depth = depth * SHRINK

    async def invoke(_model: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        frames = [
            {
                "image": f["image"],
                "depth": store.put_blob(png(np.round(depth * 1000).astype(np.uint16))),
                "intrinsics": K,
                "coverage": 1.0,
                "median_m": float(np.median(depth)),
            }
            for f in payload["frames"]
        ]
        return {"output": {"frames": frames}, "gpu_seconds": 4.0}

    runner = StepRunner(store, max_attempts=1)
    gateway = ModelGateway(depth_chain(invoke), ledger=InMemorySpendLedger(ROOMY))
    photo = await runner.run(
        single_photo_step(gateway),
        {
            "capture": store.put_blob(json.dumps(capture_doc(heading)).encode()),
            "images": store.put_blob(json.dumps({"k0": store.put_blob(jpeg())}).encode()),
        },
        {},
    )
    dim = {"value_m": 1.7, "source": "estimated", "error_band_m": 0.2}
    sofa = {
        "category": "sofa",
        "label": "Sofa",
        "confidence": 0.8,
        "frames": 1,
        "up_axis": 1,
        "box": {
            "center": [0.5, 0.4, -3.0],
            "yaw_deg": 0.0,
            "length": dim,
            "width": dim,
            "height": dim,
        },
        "views": [],
    }
    openings = [
        {
            "keyframe_id": "k0",
            "kind": "door",
            "mask": store.put_blob(png(door.astype(np.uint8) * 255)),
        }
    ]
    scaled = await runner.run(
        single_photo_scale_step(),
        {
            "frames": photo.outputs["frames"],
            "scale": photo.outputs["scale"],
            "objects": store.put_blob(json.dumps([sofa]).encode()),
            "built_ins": store.put_blob(b"[]"),
            "openings": store.put_blob(json.dumps(openings).encode()),
        },
        {},
    )
    return store, runner, photo, scaled, openings


async def test_door_and_ceiling_correct_a_room_seen_small(tmp_path: Path) -> None:
    store, _, photo, scaled, _ = await build(tmp_path)
    record = json.loads(store.read_blob(scaled.outputs["scale"]))
    assert record["outcome"] == "corrected"
    assert record["cues"]["door"] == pytest.approx(2.05 * SHRINK, abs=0.04)
    # The smallest factor that brings both into range: the door to 2.0 m.
    assert 2.0 - 1e-3 <= record["cues"]["door"] * record["factor"] <= 2.15 + 1e-3
    assert 2.6 - 1e-3 <= record["cues"]["ceiling"] * record["factor"] <= 3.3 + 1e-3
    frames = json.loads(store.read_blob(scaled.outputs["frames"]))
    before = json.loads(store.read_blob(photo.outputs["frames"]))
    assert frames["frames"][0]["c2w"][1][3] == pytest.approx(
        before["frames"][0]["c2w"][1][3] * record["factor"], abs=1e-6
    )
    (sofa,) = json.loads(store.read_blob(scaled.outputs["objects"]))
    assert sofa["box"]["length"]["value_m"] == pytest.approx(1.7 * record["factor"], abs=1e-3)
    assert (
        sofa["box"]["length"]["error_band_m"]
        >= BAND_ONE_CUE * sofa["box"]["length"]["value_m"] - 1e-3
    )
    kinds = [a["kind"] for a in record["evidence"]["anchors"]]
    assert kinds == ["geometry_model", "ceiling_prior", "door_height"]
    assert record["evidence"]["anchors_agree"] is True


async def test_the_photo_becomes_an_estimated_twin_with_open_edges(tmp_path: Path) -> None:
    store, runner, _, scaled, openings = await build(tmp_path)
    inputs = {
        "capture": store.put_blob(json.dumps(capture_doc()).encode()),
        "frames": scaled.outputs["frames"],
        "objects": scaled.outputs["objects"],
        "built_ins": scaled.outputs["built_ins"],
        "openings": store.put_blob(json.dumps(openings).encode()),
        "scale": scaled.outputs["scale"],
    }
    result = await runner.run(assemble_step(), inputs, PARAMS)
    twin = json.loads(store.read_blob(result.outputs["twin"]))
    SpaceTwin.model_validate(twin)
    assert twin["confidence"]["level"] == "estimated"
    assert twin["scale"]["needs_tape_value"] is True
    kinds = [w.get("kind", "wall") for w in twin["shell"]["walls"]]
    # The side behind the camera was not seen: unseen, never claimed open.
    assert "unseen" in kinds and "wall" in kinds and "open" not in kinds
    band = json.loads(store.read_blob(scaled.outputs["scale"]))["band_fraction"]
    for wall in twin["shell"]["walls"]:
        assert wall["length"]["error_band_m"] >= band * wall["length"]["value_m"] - 1e-3
    assert twin["direction"]["north_deg"] is not None
    assert result.meta["confidence"] == "estimated"


async def test_without_any_compass_heading_the_twin_has_no_direction(tmp_path: Path) -> None:
    store, runner, _, scaled, _ = await build(tmp_path, heading=None)
    inputs = {
        "capture": store.put_blob(json.dumps(capture_doc(None)).encode()),
        "frames": scaled.outputs["frames"],
        "objects": scaled.outputs["objects"],
        "scale": scaled.outputs["scale"],
    }
    result = await runner.run(assemble_step(), inputs, PARAMS)
    twin = json.loads(store.read_blob(result.outputs["twin"]))
    SpaceTwin.model_validate(twin)
    assert "direction" not in twin and result.meta["north_deg"] is None


def test_a_box_from_one_view() -> None:
    rng = np.random.default_rng(0)
    points = rng.uniform([0, 0, 0], [1.8, 0.8, 0.9], (600, 3))
    obs = Observation(0, "sofa", 0.9, voxelize(points, 0.05), key=0)

    instances = merge_instances(fuse([obs]))
    assert fitted_objects(instances, 1) == []  # a scan needs three frames
    (fitted,) = fitted_objects(instances, 1, min_frames=1)
    assert fitted[0] == "sofa" and fitted[2] == 1


def test_unseen_edges_are_marked_only_when_asked() -> None:
    depth, _ = render_room(1.4, 8.0)

    camera = level_camera(lift(depth, K))
    assert camera is not None
    points = to_world(lift(depth, K, stride=2), camera)
    closed = fit_space(points, "image")
    opened = fit_space(points, "image", mark_unseen=True)
    assert all("kind" not in w for w in closed.shell["walls"])
    kinds = [w.get("kind", "wall") for w in opened.shell["walls"]]
    assert kinds.count("unseen") >= 1 and "open" not in kinds
    assert len(opened.shell["surfaces"]) < len(closed.shell["surfaces"])


def test_scaling_keeps_a_box_on_the_floor() -> None:

    check = check_scale(2.3, [])
    dim = {"value_m": 0.8, "source": "estimated", "error_band_m": 0.05}
    box = {"center": [1.0, 0.4, -2.0], "yaw_deg": 0, "length": dim, "width": dim, "height": dim}
    scaled = scale_object({"box": box}, check)["box"]
    # The box's bottom stays on the floor: centre height and half height scale together.
    assert scaled["center"][1] - scaled["height"]["value_m"] / 2 == pytest.approx(0.0, abs=1e-3)
