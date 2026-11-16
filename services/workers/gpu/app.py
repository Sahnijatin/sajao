"""Modal app for the twin worker's GPU models.

Every GPU model runs in the one function `run_model`, capped at MAX_GPUS
containers, so the pipeline never holds more than three GPUs at once. Callers
reach it only through gateway providers (sajao_workers.gpu), which pin the
model, reserve spend and validate the output.

Inputs and outputs are blobs in the artifact store on the `sajao-twin` volume,
passed by digest, so a request's content hash covers the images it reads.

    uv run --with 'modal[api-proxy-support]==1.6.4' modal run services/workers/gpu/app.py::smoke
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import modal

HERE = Path(__file__).parent
SRC = HERE.parent / "src" / "sajao_workers"
MAX_GPUS = 3  # Must match sajao_workers.gpu.MAX_GPUS.

gpu_image = (
    modal.Image.from_registry("nvidia/cuda:12.4.1-cudnn-devel-ubuntu22.04", add_python="3.11")
    .apt_install("git", "libgl1", "libglib2.0-0")
    .pip_install(
        "torch==2.4.1",
        "torchvision==0.19.1",
        index_url="https://download.pytorch.org/whl/cu124",
    )
    .pip_install(
        "numpy==2.1.3",
        "pillow==11.0.0",
        "opencv-python-headless==4.10.0.84",
        "transformers==4.57.1",
        "ultralytics==8.4.214",
        "git+https://github.com/ultralytics/CLIP.git",
    )
    .env({"HF_HOME": "/vol/hf", "PYTHONUNBUFFERED": "1"})
    .add_local_dir(SRC, "/root/sajao_workers")
)

app = modal.App("sajao-twin-worker")
vol = modal.Volume.from_name("sajao-twin", create_if_missing=True)
STORE_ROOT = Path("/vol/artifacts")


class InputError(Exception):
    """The request can never succeed (missing image, unknown model)."""


_loaded: dict[str, Any] = {}


def _store() -> Any:
    from sajao_workers.steps import LocalArtifactStore

    return LocalArtifactStore(STORE_ROOT)


def _rgb(digest: str) -> Any:
    import cv2
    import numpy as np

    store = _store()
    if not store.has_blob(digest):
        raise InputError(f"image {digest[:12]} not in the store")
    data = np.frombuffer(store.read_blob(digest), np.uint8)
    bgr = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if bgr is None:
        raise InputError(f"image {digest[:12]} is not an image")
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)


def _split(model: str) -> tuple[str, str]:
    name, _, revision = model.partition("@")
    return name, revision


def _yoloe(model: str, vocabulary: list[str]) -> Any:
    import os

    from ultralytics import YOLOE

    key = f"{model}|{'.'.join(vocabulary)}"
    if key not in _loaded:
        weights = Path("/vol/models")
        weights.mkdir(parents=True, exist_ok=True)
        cwd = os.getcwd()
        os.chdir(weights)  # The text encoder downloads into the working directory.
        try:
            detector = YOLOE(_split(model)[0].replace("-seg", "-seg.pt"))
            detector.set_classes(vocabulary)
        finally:
            os.chdir(cwd)  # A working directory inside the volume blocks commits.
        _loaded[key] = detector
    return _loaded[key]


def _hf(model: str, kind: str) -> tuple[Any, Any]:
    if model not in _loaded:
        from transformers import (
            AutoModelForZeroShotObjectDetection,
            AutoProcessor,
            Sam2Model,
            Sam2Processor,
        )

        name, revision = _split(model)
        if kind == "detect":
            processor = AutoProcessor.from_pretrained(name, revision=revision)
            network = AutoModelForZeroShotObjectDetection.from_pretrained(name, revision=revision)
        else:
            processor = Sam2Processor.from_pretrained(name, revision=revision)
            network = Sam2Model.from_pretrained(name, revision=revision)
        _loaded[model] = (processor, network.cuda().eval())
    loaded: tuple[Any, Any] = _loaded[model]
    return loaded


def detect(model: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Boxes, labels and scores per frame. Labels outside the vocabulary are dropped."""
    import torch
    import torchvision
    from PIL import Image

    vocabulary = list(payload["vocabulary"])
    frames = []
    for image in payload["images"]:
        rgb = _rgb(image["image"])
        height, width = rgb.shape[:2]
        pil = Image.fromarray(rgb)
        if model.startswith("yoloe"):
            found = _yoloe(model, vocabulary).predict(pil, conf=0.25, verbose=False)[0]
            boxes, scores = found.boxes.xyxy.float(), found.boxes.conf.float()
            labels = [vocabulary[int(c)] for c in found.boxes.cls.tolist()]
        elif model.startswith("IDEA-Research/grounding-dino"):
            processor, network = _hf(model, "detect")
            inputs = processor(images=pil, text=". ".join(vocabulary) + ".", return_tensors="pt")
            with torch.no_grad():
                out = network(**inputs.to("cuda"))
            result = processor.post_process_grounded_object_detection(
                out,
                inputs.input_ids,
                threshold=0.30,
                text_threshold=0.25,
                target_sizes=[(height, width)],
            )[0]
            boxes, scores = result["boxes"].float(), result["scores"].float()
            labels = [str(x).strip() for x in result["text_labels"]]
        else:
            raise InputError(f"unknown detector {model}")
        keep = [i for i, label in enumerate(labels) if label in vocabulary]
        boxes, scores, labels = boxes[keep], scores[keep], [labels[i] for i in keep]
        if labels:
            classes = torch.tensor([vocabulary.index(x) for x in labels], device=boxes.device)
            keep = torchvision.ops.batched_nms(boxes, scores, classes, 0.5).tolist()
            boxes, scores, labels = boxes[keep], scores[keep], [labels[i] for i in keep]
        boxes[:, 0::2] = boxes[:, 0::2].clamp(0, width)
        boxes[:, 1::2] = boxes[:, 1::2].clamp(0, height)
        detections = [
            {"label": label, "score": round(float(score), 4), "box": [float(v) for v in box]}
            for label, score, box in zip(labels, scores.tolist(), boxes.tolist(), strict=True)
            if box[0] < box[2] and box[1] < box[3]
        ]
        frames.append({"image": image["image"], "detections": detections})
    return {"frames": frames}


def segment(model: str, payload: dict[str, Any]) -> dict[str, Any]:
    """One SAM 2.1 mask per box, stored as a PNG blob."""
    import cv2
    import numpy as np
    import torch
    from PIL import Image

    if not model.startswith("facebook/sam2.1"):
        raise InputError(f"unknown segmenter {model}")
    processor, network = _hf(model, "segment")
    store = _store()
    frames = []
    for frame in payload["frames"]:
        if not frame["boxes"]:
            frames.append({"image": frame["image"], "masks": []})
            continue
        pil = Image.fromarray(_rgb(frame["image"]))
        inputs = processor(images=pil, input_boxes=[frame["boxes"]], return_tensors="pt")
        with torch.no_grad():
            out = network(**inputs.to("cuda"), multimask_output=False)
        masks = processor.post_process_masks(out.pred_masks.cpu(), inputs["original_sizes"].cpu())[
            0
        ]
        masks = (masks[:, 0] > 0.5).numpy() if masks.ndim == 4 else (masks > 0.5).numpy()
        scores = out.iou_scores.cpu().reshape(-1).clamp(0, 1).tolist()
        stored = []
        for mask, score in zip(masks, scores, strict=True):
            png = cv2.imencode(".png", mask.astype(np.uint8) * 255)[1].tobytes()
            stored.append(
                {"mask": store.put_blob(png), "area": int(mask.sum()), "score": round(score, 4)}
            )
        frames.append({"image": frame["image"], "masks": stored})
    return {"frames": frames}


HANDLERS = {"twin_detect": detect, "twin_segment": segment}


@app.function(
    image=gpu_image,
    gpu="L40S",
    volumes={"/vol": vol},
    timeout=1800,
    max_containers=MAX_GPUS,
    scaledown_window=60,
)
def run_model(model: str, task: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Run one pinned model. Time includes model loading, so the charge is honest."""
    started = time.time()
    vol.reload()
    try:
        if task not in HANDLERS:
            raise InputError(f"unknown task {task}")
        output = HANDLERS[task](model, payload)
    except InputError as error:
        return {"error": str(error)}
    vol.commit()
    return {"output": output, "gpu_seconds": round(time.time() - started, 3)}


@app.local_entrypoint()
def smoke(scene: str = "arkit_living_47331265", frames: int = 6) -> None:
    """Run real ARKit frames through the detect and segment chains via the gateway."""
    import asyncio
    import hashlib
    import io
    import json

    from sajao_gateway import InMemorySpendLedger, ModelGateway, ModelRequest, SpendCaps
    from sajao_workers.gpu import INR_PER_USD
    from sajao_workers.models import VOCABULARY, detect_chain, segment_chain
    from sajao_workers.validate import check_detections, check_masks

    source = modal.Volume.from_name("sajao-twin-risk")
    names = sorted(e.path for e in source.listdir(f"scenes/{scene}/images"))
    picked = names[:: max(1, len(names) // frames)][:frames]
    images = []
    with vol.batch_upload(force=True) as upload:
        for path in picked:
            data = b"".join(source.read_file(path))
            digest = hashlib.sha256(data).hexdigest()
            upload.put_file(io.BytesIO(data), f"artifacts/blobs/{digest[:2]}/{digest}")
            images.append({"image": digest, "width": 640, "height": 480})

    async def main() -> None:
        def invoke_for(task: str):
            async def invoke(model: str, payload: Any) -> Any:
                return await run_model.remote.aio(model, task, dict(payload))

            return invoke

        caps = SpendCaps(per_user_daily_micro_inr=10**9, global_daily_micro_inr=10**9)
        ledger = InMemorySpendLedger(caps)
        payload = {"images": images, "vocabulary": list(VOCABULARY)}
        detected = await ModelGateway(detect_chain(invoke_for("twin_detect")), ledger=ledger).call(
            ModelRequest("twin_detect", "vision", "twin_detect@1", payload),
            validate=check_detections(payload),
        )
        boxes = {
            "frames": [
                {**image, "boxes": [d["box"] for d in frame["detections"]]}
                for image, frame in zip(images, detected.output["frames"], strict=True)
            ]
        }
        masked = await ModelGateway(segment_chain(invoke_for("twin_segment")), ledger=ledger).call(
            ModelRequest("twin_segment", "vision", "twin_segment@1", boxes),
            validate=check_masks(boxes),
        )
        cost = detected.cost_micro_inr + masked.cost_micro_inr
        print(
            json.dumps(
                {
                    "frames": len(images),
                    "detector": detected.provider,
                    "detections": sum(len(f["detections"]) for f in detected.output["frames"]),
                    "labels": sorted(
                        {d["label"] for f in detected.output["frames"] for d in f["detections"]}
                    ),
                    "segmenter": masked.provider,
                    "masks": sum(len(f["masks"]) for f in masked.output["frames"]),
                    "charged_inr": round(cost / 1e6, 3),
                    "charged_usd": round(cost / 1e6 / INR_PER_USD, 4),
                },
                indent=1,
            )
        )

    asyncio.run(main())
