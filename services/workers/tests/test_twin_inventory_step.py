"""The inventory step: two vision models list the room from spread-out keyframes."""

import io
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from sajao_gateway import (
    InMemorySpendLedger,
    ModelGateway,
    ProviderError,
    ProviderResult,
    SpendCaps,
)
from sajao_gateway.testing import FakeProvider
from sajao_workers.steps import LocalArtifactStore, StepRunner
from sajao_workers.twin.inventory_step import inventory_step

ROOMY = SpendCaps(per_user_daily_micro_inr=10**12, global_daily_micro_inr=10**12)


def png(array: np.ndarray) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(array).save(buf, format="PNG")
    return buf.getvalue()


def setup(tmp_path: Path, n: int = 12) -> tuple[StepRunner, str]:
    store = LocalArtifactStore(tmp_path)
    frames = []
    for i in range(n):
        yaw = 2 * math.pi * i / n
        c2w = np.eye(4)
        forward = [math.cos(yaw), math.sin(yaw), 0.0]
        down = [0.0, 0.0, -1.0]
        c2w[:3, :3] = np.column_stack([np.cross(down, forward), down, forward])
        image = store.put_blob(png(np.full((1440, 1920, 3), 10 * i, np.uint8)))
        frames.append(
            {"keyframe_id": f"kf{i}", "image": image, "width": 1920, "height": 1440,
             "intrinsics": [[1, 0, 0], [0, 1, 0], [0, 0, 1]], "c2w": c2w.tolist()}
        )  # fmt: skip
    manifest = {"up_axis": 2, "depth_source": "lidar", "frames": frames}
    return StepRunner(store, max_attempts=1), store.put_blob(json.dumps(manifest).encode())


def listing(*names: tuple[str, str]) -> ProviderResult:
    items = [{"name": n, "type": t, "count": 1, "prompts": []} for n, t in names]
    return ProviderResult(output={"items": items}, cost_micro_inr=5_000)


def gateway(provider: FakeProvider) -> ModelGateway:
    return ModelGateway([provider], ledger=InMemorySpendLedger(ROOMY))


async def test_both_models_list_from_eight_small_keyframes_and_the_lists_merge(
    tmp_path: Path,
) -> None:
    runner, manifest = setup(tmp_path)
    gemini = FakeProvider("gemini", [listing(("sofa", "furniture"), ("geyser", "fixture"))],
                          model="gemini-3-flash-preview")  # fmt: skip
    claude = FakeProvider("claude", [listing(("Sofa", "furniture"), ("wall clock", "wall_item"))],
                          model="claude-opus-5-5")  # fmt: skip

    result = await runner.run(
        inventory_step(gateway(gemini), gateway(claude)), {"frames": manifest}, {}
    )

    inventory: dict[str, Any] = json.loads(runner.store.read_blob(result.outputs["inventory"]))
    assert inventory["listed_by"] == ["gemini-3-flash-preview", "claude-opus-5-5"]
    by_name = {i["name"]: i["listed_by"] for i in inventory["items"]}
    assert by_name == {
        "sofa": ["claude-opus-5-5", "gemini-3-flash-preview"],
        "geyser": ["gemini-3-flash-preview"],
        "wall clock": ["claude-opus-5-5"],
    }
    sent = gemini.calls[0]
    assert len(sent.blobs) == 8
    assert max(Image.open(io.BytesIO(sent.blobs[0])).size) == 1024
    assert sent.prompt_id == "twin_inventory@2"
    assert "how many chairs are around" in sent.payload["prompt"]  # seats counted per group
    assert result.cost_micro_inr == 10_000
    assert result.meta["keyframes"] == len(inventory["keyframes"]) == 8


async def test_the_list_stands_when_the_cross_check_fails(tmp_path: Path) -> None:
    runner, manifest = setup(tmp_path)
    gemini = FakeProvider(
        "gemini", [listing(("sofa", "furniture"))], model="gemini-3-flash-preview"
    )
    claude = FakeProvider(
        "claude", [ProviderError("down", retryable=False)], model="claude-opus-5-5"
    )

    result = await runner.run(
        inventory_step(gateway(gemini), gateway(claude)), {"frames": manifest}, {}
    )

    inventory = json.loads(runner.store.read_blob(result.outputs["inventory"]))
    assert inventory["listed_by"] == ["gemini-3-flash-preview"]
    assert result.meta["failed"] == ["cross_check"]
