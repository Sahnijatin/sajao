"""The single-photo step through the gateway, with a fake GPU: no Modal, no keys."""

import io
import json
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
from sajao_workers.models import MOGE3, depth_chain
from sajao_workers.steps import LocalArtifactStore, StepFailedError, StepRunner
from sajao_workers.twin.single_photo_step import fov_from_exif, single_photo_step
from sajao_workers.twin.synthetic import H, K, W, render_room
from sajao_workers.validate import check_depths

ROOMY = SpendCaps(per_user_daily_micro_inr=10**12, global_daily_micro_inr=10**12)


def jpeg(width: int = W, height: int = H, focal_35mm: int | None = None) -> bytes:
    image = Image.new("RGB", (width, height), (200, 190, 170))
    exif = Image.Exif()
    if focal_35mm is not None:
        exif.get_ifd(0x8769)[0xA405] = focal_35mm
    buf = io.BytesIO()
    image.save(buf, format="JPEG", exif=exif)
    return buf.getvalue()


def png_mm(depth: np.ndarray) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(np.round(depth * 1000).astype(np.uint16)).save(buf, format="PNG")
    return buf.getvalue()


def capture(store: LocalArtifactStore, photo: bytes, n: int = 1) -> dict[str, str]:
    keyframes = [
        {"id": f"k{i}", "image": f"u/k{i}.jpg", "captured_at_ms": 0, "sharpness": 0}
        for i in range(n)
    ]
    doc = {"package": {"ar": {"tracking": "none"}, "keyframes": keyframes}}
    images = {k["id"]: store.put_blob(photo) for k in keyframes}
    return {
        "capture": store.put_blob(json.dumps(doc).encode()),
        "images": store.put_blob(json.dumps(images).encode()),
    }


def fake_gpu(store: LocalArtifactStore, depth: np.ndarray, seen: list[Any]) -> Any:
    async def invoke(model: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        seen.append((model, payload))
        frames = [
            {
                "image": f["image"],
                "depth": store.put_blob(png_mm(depth)),
                "intrinsics": f["intrinsics"] or K,
                "coverage": 1.0,
                "median_m": float(np.median(depth)),
            }
            for f in payload["frames"]
        ]
        return {"output": {"frames": frames}, "gpu_seconds": 4.0}

    return invoke


async def run(store: LocalArtifactStore, inputs: dict[str, str], depth: np.ndarray) -> Any:
    seen: list[Any] = []
    gateway = ModelGateway(
        depth_chain(fake_gpu(store, depth, seen)), ledger=InMemorySpendLedger(ROOMY)
    )
    result = await StepRunner(store, max_attempts=1).run(single_photo_step(gateway), inputs, {})
    return result, seen


async def test_one_photo_gives_a_camera_on_the_floor(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path)
    depth, _ = render_room(1.4, 10.0)
    result, seen = await run(store, capture(store, jpeg()), depth)

    assert seen[0][0] == MOGE3
    assert seen[0][1]["frames"][0]["intrinsics"] is None  # no EXIF: the model estimates it
    manifest = json.loads(store.read_blob(result.outputs["frames"]))
    assert manifest["single_view"] is True and manifest["depth_source"] == "image"
    (frame,) = manifest["frames"]
    assert np.allclose(frame["intrinsics"], K, atol=1e-3)
    assert frame["c2w"][1][3] == pytest.approx(1.4, abs=0.02)
    scale = json.loads(store.read_blob(result.outputs["scale"]))
    assert scale["ceiling_m"] == pytest.approx(2.8, abs=0.03)
    assert result.meta["fov_from"] == "depth_model"
    assert result.meta["tilt_deg"] == pytest.approx(10.0, abs=0.5)


async def test_exif_focal_length_sets_the_camera(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path)
    depth, _ = render_room(1.4, 10.0)
    result, seen = await run(store, capture(store, jpeg(focal_35mm=26)), depth)
    k = seen[0][1]["frames"][0]["intrinsics"]
    assert k is not None and k[0][2] == W / 2
    assert result.meta["fov_from"] == "exif"


def test_fov_from_exif() -> None:
    assert fov_from_exif(jpeg(focal_35mm=26)) == pytest.approx(69.4, abs=0.1)
    portrait = fov_from_exif(jpeg(240, 320, focal_35mm=26))
    assert portrait is not None and portrait < 60.0
    assert fov_from_exif(jpeg()) is None
    assert fov_from_exif(b"not a photo") is None


async def test_a_photo_without_floor_fails_with_a_reason(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path)
    wall = np.full((H, W), 2.5)
    with pytest.raises(StepFailedError) as raised:
        await run(store, capture(store, jpeg()), wall)
    assert getattr(raised.value.__cause__, "code", None) == "floor_not_visible"


async def test_more_than_one_photo_is_not_this_path(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path)
    depth, _ = render_room(1.4, 10.0)
    with pytest.raises(StepFailedError) as raised:
        await run(store, capture(store, jpeg(), n=2), depth)
    assert getattr(raised.value.__cause__, "code", None) == "photo_missing"


def test_estimated_intrinsics_must_be_a_phone_camera(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path)
    payload = {
        "frames": [{"image": store.put_blob(b"a"), "width": W, "height": H, "intrinsics": None}]
    }
    good = {"image": payload["frames"][0]["image"], "depth": store.put_blob(b"d"), "coverage": 1.0}
    check = check_depths(payload)
    check(ProviderResult({"frames": [{**good, "median_m": 3.0, "intrinsics": K}]}))
    for bad in (
        None,
        [[5.0, 0, 160], [0, 5.0, 120], [0, 0, 1]],
        [[300.0, 0, 900], [0, 300, 120], [0, 0, 1]],
    ):
        with pytest.raises(InvalidOutputError):
            check(ProviderResult({"frames": [{**good, "median_m": 3.0, "intrinsics": bad}]}))
