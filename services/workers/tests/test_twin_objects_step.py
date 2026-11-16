"""The objects step end to end: gateway detect and segment, then lift and fuse, durably."""

import io
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from PIL import Image

from sajao_gateway import InMemorySpendLedger, ModelGateway, SpendCaps
from sajao_workers.models import detect_chain, segment_chain
from sajao_workers.steps import LocalArtifactStore, StepFailedError, StepRunner
from sajao_workers.twin.objects_step import objects_step

W, H, F = 320, 240, 250.0
K = [[F, 0.0, W / 2], [0.0, F, H / 2], [0.0, 0.0, 1.0]]
ROOMY = SpendCaps(per_user_daily_micro_inr=10**12, global_daily_micro_inr=10**12)


def png(array: np.ndarray) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(array).save(buf, format="PNG")
    return buf.getvalue()


def camera_at(x: float) -> list[list[float]]:
    return [[1.0, 0.0, 0.0, x], [0.0, -1.0, 0.0, 1.2], [0.0, 0.0, -1.0, 0.0], [0, 0, 0, 1.0]]


def sofa_mask(x: float) -> np.ndarray:
    ys, xs = np.mgrid[0:H, 0:W]
    wx = x + (xs - W / 2) * 3.0 / F
    wy = 1.2 - (ys - H / 2) * 3.0 / F
    mask: np.ndarray = (wx > -0.5) & (wx < 0.5) & (wy > 0.0) & (wy < 0.8)
    return mask


class FakeGpu:
    """Stands in for the Modal GPU function: finds the sofa and writes its masks."""

    def __init__(
        self, store: LocalArtifactStore, masks: dict[str, np.ndarray], label: str = "sofa"
    ) -> None:
        self.store, self.masks, self.calls = store, masks, []  # type: ignore[var-annotated]
        self.label = label
        self.vocabulary: list[str] = []
        self.detect_payloads: list[dict[str, Any]] = []

    async def __call__(self, model: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        self.calls.append(model)
        if "images" in payload:
            self.vocabulary = list(payload["vocabulary"])
            self.detect_payloads.append(dict(payload))
            frames = []
            for image in payload["images"]:
                ys, xs = np.nonzero(self.masks[image["image"]])
                box = [float(xs.min()), float(ys.min()), float(xs.max() + 1), float(ys.max() + 1)]
                found = [{"label": self.label, "score": 0.9, "box": box}]
                frames.append(
                    {
                        "image": image["image"],
                        "detections": found if self.label in self.vocabulary else [],
                    }
                )
            return {"output": {"frames": frames}, "gpu_seconds": 1.0}
        frames = []
        for frame in payload["frames"]:
            mask = self.masks[frame["image"]]
            digest = self.store.put_blob(png(mask.astype(np.uint8) * 255))
            frames.append(
                {
                    "image": frame["image"],
                    "masks": [{"mask": digest, "area": int(mask.sum()), "score": 0.95}],
                }
            )
        return {"output": {"frames": frames}, "gpu_seconds": 2.0}


def setup(tmp_path: Path, depth: bool = True) -> tuple[StepRunner, FakeGpu, str]:
    store = LocalArtifactStore(tmp_path)
    runner = StepRunner(store, max_attempts=1)
    masks, frames = {}, []
    for i in range(4):
        x = -0.2 + 0.1 * i
        image = store.put_blob(png(np.full((H, W, 3), 40 + i, np.uint8)))
        masks[image] = sofa_mask(x)
        depth_blob = store.put_blob(png(np.full((H, W), 3000, np.uint16))) if depth else None
        frames.append(
            {
                "keyframe_id": f"kf{i}",
                "image": image,
                "width": W,
                "height": H,
                "intrinsics": K,
                "c2w": camera_at(x),
                "depth": depth_blob,
            }
        )
    manifest = {"up_axis": 1, "depth_source": "lidar", "frames": frames}
    return runner, FakeGpu(store, masks), store.put_blob(json.dumps(manifest).encode())


def gateways(gpu: FakeGpu) -> tuple[ModelGateway, ModelGateway]:
    ledger = InMemorySpendLedger(ROOMY)
    return (
        ModelGateway(detect_chain(gpu), ledger=ledger),
        ModelGateway(segment_chain(gpu), ledger=ledger),
    )


async def test_the_step_finds_the_sofa_and_charges_the_gpu_calls(tmp_path: Path) -> None:
    runner, gpu, manifest = setup(tmp_path)

    result = await runner.run(objects_step(*gateways(gpu)), {"frames": manifest}, {})

    objects = json.loads(runner.store.read_blob(result.outputs["objects"]))
    assert [o["category"] for o in objects] == ["sofa"]
    assert objects[0]["box"]["length"]["value_m"] == pytest.approx(1.0, abs=0.1)
    assert result.meta["objects"] == 1
    assert (result.meta["detector"], result.meta["segmenter"]) == ("yoloe", "sam2.1-large")
    assert isinstance(result.meta["fusion"], dict)
    assert result.cost_micro_inr > 0
    assert len(gpu.calls) == 2


async def test_a_rerun_costs_nothing_and_calls_no_gpu(tmp_path: Path) -> None:
    runner, gpu, manifest = setup(tmp_path)
    first = await runner.run(objects_step(*gateways(gpu)), {"frames": manifest}, {})

    again = await runner.run(objects_step(*gateways(gpu)), {"frames": manifest}, {})

    assert again.cached and again.cost_micro_inr == 0
    assert again.outputs == first.outputs
    assert len(gpu.calls) == 2


async def test_frames_without_depth_stop_with_a_clear_reason(tmp_path: Path) -> None:
    runner, gpu, manifest = setup(tmp_path, depth=False)

    with pytest.raises(StepFailedError, match="no depth"):
        await runner.run(objects_step(*gateways(gpu)), {"frames": manifest}, {})
    assert gpu.calls == []  # checked before any GPU call


async def test_doors_and_windows_are_found_in_the_same_pass_and_kept_out_of_objects(
    tmp_path: Path,
) -> None:
    runner, gpu, manifest = setup(tmp_path)
    gpu.label = "window"

    result = await runner.run(objects_step(*gateways(gpu)), {"frames": manifest}, {})

    assert {"door", "window"} <= set(gpu.vocabulary)
    assert json.loads(runner.store.read_blob(result.outputs["objects"])) == []
    openings = json.loads(runner.store.read_blob(result.outputs["openings"]))
    assert [o["kind"] for o in openings] == ["window"] * 4
    assert {o["keyframe_id"] for o in openings} == {"kf0", "kf1", "kf2", "kf3"}
    assert runner.store.has_blob(openings[0]["mask"])
    assert result.meta["opening_masks"] == 4


def inventory_blob(runner: StepRunner, *items: tuple[str, str, list[str]]) -> str:
    inventory = {
        "listed_by": ["gemini-3-flash-preview"],
        "items": [
            {
                "name": n,
                "type": t,
                "count": 1,
                "prompts": p,
                "listed_by": ["gemini-3-flash-preview"],
            }
            for n, t, p in items
        ],
        "keyframes": ["kf0"],
    }
    return runner.store.put_blob(json.dumps(inventory).encode())


async def test_the_inventory_names_what_is_looked_for_and_every_object_gets_its_type(
    tmp_path: Path,
) -> None:
    runner, gpu, manifest = setup(tmp_path)
    inventory = inventory_blob(
        runner, ("sofa", "furniture", ["couch"]), ("geyser", "fixture", ["water heater"])
    )

    result = await runner.run(
        objects_step(*gateways(gpu)), {"frames": manifest, "inventory": inventory}, {}
    )

    first, retry = gpu.detect_payloads
    assert first["vocabulary"] == ["sofa", "geyser", "door", "window"]
    assert (retry["vocabulary"], retry["prompts"]) == (["geyser"], ["water heater"])
    assert retry["min_score"] < 0.2
    (sofa,) = json.loads(runner.store.read_blob(result.outputs["objects"]))
    assert sofa["object_type"] == "furniture"
    placement = json.loads(runner.store.read_blob(result.outputs["inventory"]))
    assert placement["listed_by"] == ["gemini-3-flash-preview"]
    assert placement["items_listed"] == 2
    (geyser,) = placement["unplaced"]
    assert geyser["name"] == "geyser" and geyser["reason"] == "not_detected"
    assert geyser["tried"] == ["yoloe: geyser", "yoloe: water heater (min score 0.1)"]
    assert result.meta["unplaced"] == 1


async def test_built_ins_are_kept_apart_for_the_shell(tmp_path: Path) -> None:
    runner, gpu, manifest = setup(tmp_path)
    inventory = inventory_blob(runner, ("sofa", "built_in", []))

    result = await runner.run(
        objects_step(*gateways(gpu)), {"frames": manifest, "inventory": inventory}, {}
    )

    assert json.loads(runner.store.read_blob(result.outputs["objects"])) == []
    (built_in,) = json.loads(runner.store.read_blob(result.outputs["built_ins"]))
    assert built_in["category"] == "sofa"
    assert len(gpu.detect_payloads) == 1  # everything was placed: no retry
