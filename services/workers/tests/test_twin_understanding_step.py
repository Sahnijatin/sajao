"""The room understanding step: footprints, keep or replace, free floor and hero masks, durably."""

import io
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from sajao_gateway import InMemorySpendLedger, ModelGateway, SpendCaps
from sajao_schemas.generated.v1 import SpaceTwin
from sajao_workers.models import segment_chain
from sajao_workers.steps import LocalArtifactStore, StepRunner
from sajao_workers.twin.assemble import storage_key
from sajao_workers.twin.understanding_step import understanding_step

FIXTURE = Path(__file__).parents[3] / "packages/schemas/fixtures/v1/valid/space-twin.json"
W, H, F = 640, 480, 400.0
K = [[F, 0.0, W / 2], [0.0, F, H / 2], [0.0, 0.0, 1.0]]


def twin() -> dict[str, Any]:
    doc: dict[str, Any] = json.loads(FIXTURE.read_text())
    for obj in [*doc["objects"], *doc["shell"].get("built_ins", [])]:
        for key in ("footprint", "redesign", "hero_masks"):
            obj.pop(key, None)
    doc.pop("free_floor", None)
    return doc


def camera(x: float) -> list[list[float]]:
    """A level OpenCV camera at (x, 0, 1.4) in a z-up world, looking along +y."""
    c2w = np.eye(4)
    c2w[:3, :3] = np.column_stack([[1.0, 0.0, 0.0], [0.0, 0.0, -1.0], [0.0, 1.0, 0.0]])
    c2w[:3, 3] = [x, 0.0, 1.4]
    return c2w.tolist()


def world_box(x: float, y: float) -> dict[str, Any]:
    dim = {"value_m": 1.0, "source": "estimated", "error_band_m": 0.05}
    return {"center": [x, y, 0.4], "yaw_deg": 0.0, "length": dim, "width": dim,
            "height": {**dim, "value_m": 0.8}}  # fmt: skip


ROOMY = SpendCaps(per_user_daily_micro_inr=10**12, global_daily_micro_inr=10**12)


def png(array: np.ndarray) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(array).save(buf, format="PNG")
    return buf.getvalue()


class FakeSam:
    def __init__(self, store: LocalArtifactStore) -> None:
        self.store, self.payloads = store, []  # type: ignore[var-annotated]

    async def __call__(self, model: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        self.payloads.append(payload)
        frames = []
        for frame in payload["frames"]:
            masks = []
            for x0, y0, x1, y1 in frame["boxes"]:
                mask = np.zeros((frame["height"], frame["width"]), np.uint8)
                mask[int(y0) : int(y1), int(x0) : int(x1)] = 255
                masks.append({"mask": self.store.put_blob(png(mask)), "area": int((mask > 0).sum()),
                              "score": 0.9})  # fmt: skip
            frames.append({"image": frame["image"], "masks": masks})
        return {"output": {"frames": frames}, "gpu_seconds": 1.0}


async def test_hero_masks_come_from_the_detector_or_one_prompted_call(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path)
    doc = twin()
    doc["viewing"]["hero_views"][0]["keyframe_id"] = "k1"
    detected = store.put_blob(png(np.full((H, W), 255, np.uint8)))
    objects = [
        {
            "up_axis": 2,
            "box": world_box(0.0, 3.0),
            "views": [{"keyframe_id": "k1", "mask": detected}],
        },
        {"up_axis": 2, "box": world_box(0.6, 3.5), "views": []},
    ]
    depth = store.put_blob(png(np.full((H, W), 6000, np.uint16)))
    image = store.put_blob(png(np.full((H, W, 3), 90, np.uint8)))
    manifest = {"up_axis": 2, "depth_source": "lidar", "frames": [
        {"keyframe_id": "k1", "image": image, "width": W, "height": H, "intrinsics": K,
         "c2w": camera(0.0), "depth": depth}]}  # fmt: skip
    sam = FakeSam(store)
    gateway = ModelGateway(segment_chain(sam), ledger=InMemorySpendLedger(ROOMY))
    inputs = {
        "twin": store.put_blob(json.dumps(doc).encode()),
        "objects": store.put_blob(json.dumps(objects).encode()),
        "frames": store.put_blob(json.dumps(manifest).encode()),
    }

    result = await StepRunner(store, max_attempts=1).run(understanding_step(gateway), inputs, {})

    out = json.loads(store.read_blob(result.outputs["twin"]))
    SpaceTwin.model_validate(out)
    sofa, almirah = out["objects"]
    assert [m["source"] for m in sofa["hero_masks"]] == ["detected"]
    assert sofa["hero_masks"][0]["mask"] == storage_key(detected)
    assert [m["source"] for m in almirah["hero_masks"]] == ["prompted"]
    assert len(sam.payloads) == 1 and len(sam.payloads[0]["frames"][0]["boxes"]) == 1
    assert "free_floor" in out and all("footprint" in o for o in out["objects"])
    assert result.meta["hero_masks"] == {"detected": 1, "prompted": 1}
    assert result.cost_micro_inr > 0
