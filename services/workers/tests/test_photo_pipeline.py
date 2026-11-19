"""One photo through the durable pipeline to a stored SpaceTwin, with fake models."""

import io
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from PIL import Image

from sajao_gateway import InMemorySpendLedger, ModelGateway, ProviderResult, SpendCaps
from sajao_gateway.testing import FakeProvider
from sajao_schemas.generated.v1 import SpaceTwin
from sajao_workers import pipeline
from sajao_workers.models import depth_chain, detect_chain, segment_chain
from sajao_workers.photo_pipeline import PhotoModels, photo_room_stages
from sajao_workers.pipeline import MEASURE, is_single_photo, run_room
from sajao_workers.steps import LocalArtifactStore, StepRunner
from sajao_workers.twin.synthetic import SOFA, H, K, W, render_scene

ROOM = "5e2f8a1c-3b4d-4e6f-8a9b-0c1d2e3f4a5b"
ROOMY = SpendCaps(per_user_daily_micro_inr=10**12, global_daily_micro_inr=10**12)


def png(array: np.ndarray) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(array).save(buf, format="PNG")
    return buf.getvalue()


def jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (W, H), (190, 180, 160)).save(buf, format="JPEG")
    return buf.getvalue()


class Board:
    def __init__(self) -> None:
        self.moves: list[tuple[str, str, str | None]] = []
        self.twin: dict[str, Any] | None = None

    async def set_stage(
        self,
        room_id: str,
        stage: str,
        status: str,
        detail: str | None = None,
        request_id: str | None = None,
    ) -> None:
        self.moves.append((stage, status, detail))

    async def set_space_twin(self, room_id: str, twin: dict[str, Any]) -> None:
        self.twin = twin


class Files:
    def read(self, storage_key: str) -> bytes:
        assert storage_key == "u/photo.jpg"
        return jpeg()


def capture(keyframes: int = 1) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "id": "7f9c2b1e-4c1d-4f3a-9a77-1e2d3c4b5a60",
        "user_id": "9a8b7c6d-5e4f-4a3b-8c2d-1e0f9a8b7c6d",
        "created_at": "2026-11-18T10:00:00Z",
        "device": {"platform": "android", "tier": "budget", "has_ar": False},
        "media": [
            {
                "id": "5b1d2c3e-4f5a-4b6c-8d7e-9f0a1b2c3d4e",
                "kind": "photo",
                "origin": "camera",
                "storage_key": "u/photo.jpg",
                "width_px": W,
                "height_px": H,
                "has_ar_pose": False,
                "compass_heading_deg": 75.0,
            }
        ],
        "package": {
            "ar": {"tracking": "none", "lidar": False, "depth": False},
            "keyframes": [
                {"id": f"k{i}", "image": "u/photo.jpg", "captured_at_ms": 0, "sharpness": 1}
                for i in range(keyframes)
            ],
            "detections": [],
            "sensor_log": "u/s.jsonl",
        },
    }


class FakeGpu:
    """Metric depth, detection and segmentation of the synthetic room with a sofa."""

    def __init__(self, store: LocalArtifactStore) -> None:
        self.store = store
        self.depth, self.masks = render_scene(1.35, 8.0, boxes={"sofa": SOFA})
        self.tasks: list[str] = []

    def _box(self, mask: np.ndarray) -> list[float]:
        ys, xs = np.nonzero(mask)
        return [float(xs.min()), float(ys.min()), float(xs.max() + 1), float(ys.max() + 1)]

    def _mask_for(self, box: list[float]) -> np.ndarray:
        x0, y0, x1, y1 = (round(v) for v in box)
        rect = np.zeros((H, W), bool)
        rect[max(0, y0) : y1, max(0, x0) : x1] = True
        best = max(self.masks.values(), key=lambda m: int((m & rect).sum()))
        return best & rect if (best & rect).any() else rect

    async def __call__(self, model: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        if "images" in payload:
            self.tasks.append("detect")
            vocabulary = set(payload["vocabulary"])
            found = [
                {"label": name, "score": 0.9, "box": self._box(mask)}
                for name, mask in self.masks.items()
                if name in vocabulary
            ]
            frames = [{"image": i["image"], "detections": found} for i in payload["images"]]
            return {"output": {"frames": frames}, "gpu_seconds": 1.0}
        frames = payload["frames"]
        if "boxes" in frames[0]:
            self.tasks.append("segment")
            out = []
            for f in frames:
                masks = []
                for box in f["boxes"]:
                    m = self._mask_for(box)
                    digest = self.store.put_blob(png(m.astype(np.uint8) * 255))
                    masks.append({"mask": digest, "area": int(m.sum()), "score": 0.9})
                out.append({"image": f["image"], "masks": masks})
            return {"output": {"frames": out}, "gpu_seconds": 1.0}
        self.tasks.append("depth")
        digest = self.store.put_blob(png(np.round(self.depth * 1000).astype(np.uint16)))
        out = [
            {
                "image": f["image"],
                "depth": digest,
                "intrinsics": f["intrinsics"] or K,
                "coverage": 1.0,
                "median_m": float(np.median(self.depth)),
            }
            for f in frames
        ]
        return {"output": {"frames": out}, "gpu_seconds": 3.0}


def models(store: LocalArtifactStore) -> tuple[PhotoModels, FakeGpu]:
    gpu = FakeGpu(store)
    ledger = InMemorySpendLedger(ROOMY)
    items = [{"name": "sofa", "type": "furniture", "count": 1, "prompts": []}]
    listing = ProviderResult(output={"items": items}, cost_micro_inr=5_000)
    return (
        PhotoModels(
            depth=ModelGateway(depth_chain(gpu), ledger=ledger),
            lister=ModelGateway([FakeProvider("lister", [listing])], ledger=ledger),
            checker=ModelGateway([FakeProvider("checker", [listing])], ledger=ledger),
            detect=ModelGateway(detect_chain(gpu), ledger=ledger),
            segment=ModelGateway(segment_chain(gpu), ledger=ledger),
        ),
        gpu,
    )


RENDER_MINIMUM = (pipeline.MIN_PHOTO_LONG_EDGE_PX, pipeline.MIN_PHOTO_SHORT_EDGE_PX)


@pytest.fixture(autouse=True)
def small_scene(monkeypatch: pytest.MonkeyPatch) -> None:
    """The synthetic scene is 320 by 240; the render's minimum is checked on its own."""
    monkeypatch.setattr(pipeline, "MIN_PHOTO_LONG_EDGE_PX", W)
    monkeypatch.setattr(pipeline, "MIN_PHOTO_SHORT_EDGE_PX", H)


async def test_a_photo_below_the_renders_minimum_fails_with_its_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(pipeline, "MIN_PHOTO_LONG_EDGE_PX", RENDER_MINIMUM[0])
    monkeypatch.setattr(pipeline, "MIN_PHOTO_SHORT_EDGE_PX", RENDER_MINIMUM[1])
    assert RENDER_MINIMUM == (1024, 576)
    board = Board()
    store = LocalArtifactStore(tmp_path)
    stages = photo_room_stages(models(store)[0])
    run = await run_room(StepRunner(store), board, Files(), ROOM, capture(), (MEASURE,), stages)
    assert run.outcome == "failed"
    assert board.moves == [("measure", "failed", "photo_too_small")]


async def test_a_photo_not_in_storage_fails_as_an_incomplete_upload(tmp_path: Path) -> None:
    class Missing:
        def read(self, storage_key: str) -> bytes:
            raise FileNotFoundError(storage_key)

    board = Board()
    store = LocalArtifactStore(tmp_path)
    stages = photo_room_stages(models(store)[0])
    run = await run_room(StepRunner(store), board, Missing(), ROOM, capture(), (MEASURE,), stages)
    assert run.outcome == "failed"
    assert board.moves == [("measure", "failed", "upload_incomplete")]


def test_only_one_photo_without_ar_takes_the_photo_path() -> None:
    assert is_single_photo(capture())
    assert not is_single_photo(capture(keyframes=2))
    scan = capture()
    scan["package"]["ar"]["tracking"] = "arcore"
    assert not is_single_photo(scan)


async def test_one_photo_becomes_an_estimated_twin(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path)
    photo_models, gpu = models(store)
    board = Board()
    stages = photo_room_stages(photo_models)

    run = await run_room(
        StepRunner(store, max_attempts=1), board, Files(), ROOM, capture(), (MEASURE,), stages
    )

    assert run.outcome == "done", board.moves
    assert board.twin is not None
    twin = SpaceTwin.model_validate(board.twin)
    assert twin.confidence is not None and twin.confidence.level == "estimated"
    assert [o.category for o in twin.objects] == ["sofa"]
    sofa = twin.objects[0]
    assert sofa.hero_masks, "the photo is the hero view and the sofa has its mask there"
    outline = sofa.hero_masks[0].outline
    assert outline and len(outline[0].root) >= 4  # the app draws it without the mask file
    # The sofa stands on the left of the photo.
    assert max(p.x for p in outline[0].root) < 0.5
    assert [w.kind or "wall" for w in twin.shell.walls].count("open") >= 1
    # The app sees two rows, each done once, in order.
    done = [(s, st) for s, st, _ in board.moves if st == "done"]
    assert done == [("measure", "done"), ("inventory", "done")]
    assert gpu.tasks[0] == "depth"


async def test_a_run_again_calls_no_model(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path)
    photo_models, gpu = models(store)
    stages = photo_room_stages(photo_models)
    runner = StepRunner(store, max_attempts=1)
    await run_room(runner, Board(), Files(), ROOM, capture(), (MEASURE,), stages)
    calls = len(gpu.tasks)

    board = Board()
    again = await run_room(runner, board, Files(), ROOM, capture(), (MEASURE,), stages)

    assert again.outcome == "done" and len(gpu.tasks) == calls
    assert all(st != "running" for _, st, _ in board.moves)


async def test_without_photo_stages_a_photo_still_waits(tmp_path: Path) -> None:
    board = Board()
    run = await run_room(
        StepRunner(LocalArtifactStore(tmp_path), max_attempts=1),
        board,
        Files(),
        ROOM,
        capture(),
        (MEASURE,),
    )
    assert run.outcome == "failed"
    assert board.moves == [("measure", "failed", "no_ar_data")]
