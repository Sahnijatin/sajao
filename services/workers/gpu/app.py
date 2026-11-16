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
GATEWAY = HERE.parent.parent / "gateway" / "src" / "sajao_gateway"
SCHEMAS = HERE.parent.parent.parent / "packages" / "schemas" / "python" / "sajao_schemas"
SPIKE = HERE.parent.parent / "spikes" / "twin-risk"
MAX_GPUS = 3  # Must match sajao_workers.gpu.MAX_GPUS: model and splat functions share it.
MODEL_GPUS = 2
SPLAT_GPUS = MAX_GPUS - MODEL_GPUS

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

# Splat training: the SJ-116 spike's image recipe, with gsplat also built for the
# A100 (gsplat is built from source for this torch).
MAPANYTHING_REF = "3d10cf7a3016fc0f9bb13a071ee66c47b10be0d9"

splat_base = (
    modal.Image.from_registry("nvidia/cuda:12.4.1-cudnn-devel-ubuntu22.04", add_python="3.11")
    .apt_install(
        "git", "ffmpeg", "libgl1", "libglib2.0-0", "unzip", "curl", "pigz", "build-essential"
    )
    .pip_install(
        "torch==2.4.1",
        "torchvision==0.19.1",
        "torchaudio==2.4.1",
        index_url="https://download.pytorch.org/whl/cu124",
    )
    # Keep later installs from replacing the torch that gsplat is compiled against.
    .run_commands(
        "printf 'torch==2.4.1\\ntorchvision==0.19.1\\ntorchaudio==2.4.1\\nnumpy==2.1.3\\n' > /constraints.txt"  # noqa: E501 (copied verbatim: same image layer)
    )
    .env({"PIP_CONSTRAINT": "/constraints.txt"})
    .pip_install("numpy==2.1.3", "ninja==1.11.1.3", "jaxtyping==0.2.36", "rich==13.9.4")
    # No prebuilt gsplat wheel exists for Python 3.11 with torch 2.4, so build it
    # here for T4 (7.5), A100 (8.0, the splat function's fallback), A10G (8.6),
    # L4 and L40S (8.9). The spike's list lacked 8.0: a run that fell back to an
    # A100 failed with "no kernel image".
    .env({"TORCH_CUDA_ARCH_LIST": "7.5;8.0;8.6;8.9", "MAX_JOBS": "8"})
    .run_commands("pip install --no-build-isolation gsplat==1.5.3")
    .pip_install(
        "transformers==4.57.1",
        "pillow==11.0.0",
        "pytorch-msssim==1.0.0",
        "open3d==0.19.0",
        "trimesh==4.5.3",
        "pycolmap==3.10.0",
        f"mapanything @ git+https://github.com/facebookresearch/map-anything@{MAPANYTHING_REF}",
    )
    .pip_install("opencv-python-headless==4.10.0.84", "numpy==2.1.3")
    .pip_install(
        "ultralytics==8.4.214",
        "git+https://github.com/ultralytics/CLIP.git",
        "opencv-python-headless==4.10.0.84",
        "numpy==2.1.3",
    )
    # gsplat compiles its CUDA kernels on first use; keep them on the volume.
    .env(
        {
            "HF_HOME": "/vol/hf",
            "PYTHONUNBUFFERED": "1",
            "TORCH_EXTENSIONS_DIR": "/root/torch_extensions",
        }
    )
)
splat_image = (
    splat_base.add_local_dir(SRC, "/root/sajao_workers")
    .add_local_file(HERE / "splat_gpu.py", "/root/splat_gpu.py")
    .add_local_file(HERE / "removal_gpu.py", "/root/removal_gpu.py")
)

# Phone splats: PlayCanvas splat-transform on CPU, pinned as in the SJ-116 spike.
compress_image = (
    modal.Image.debian_slim(python_version="3.13")
    .apt_install("curl", "ca-certificates", "gnupg")
    .run_commands(
        "curl -fsSL https://deb.nodesource.com/setup_22.x | bash -",
        "apt-get install -y nodejs",
        "npm install -g @playcanvas/splat-transform@3.11.2",
    )
    .env({"PYTHONUNBUFFERED": "1"})
    .add_local_dir(SRC, "/root/sajao_workers")
)

# Orchestration runs on CPU: it calls the GPU function only through the gateway.
cpu_image = (
    modal.Image.debian_slim(python_version="3.13")
    .pip_install("numpy==2.2.6", "pillow==11.3.0", "opencv-python-headless==4.12.0.88")
    .pip_install("pydantic==2.14.3")
    .env({"PYTHONUNBUFFERED": "1"})
    .add_local_dir(SRC, "/root/sajao_workers")
    .add_local_dir(GATEWAY, "/root/sajao_gateway")
    .add_local_dir(SCHEMAS, "/root/sajao_schemas")
    # Ground truth and scoring for the smoke runs only (public datasets, internal evaluation).
    .add_local_dir(SPIKE / "src" / "twin_risk", "/root/twin_risk")
    .add_local_dir(SPIKE / "gpu" / "twin_gpu", "/root/twin_gpu")
)

app = modal.App("sajao-twin-worker")
vol = modal.Volume.from_name("sajao-twin", create_if_missing=True)
spike_vol = modal.Volume.from_name("sajao-twin-risk")
STORE_ROOT = Path("/vol/artifacts")
# Splat training state, so a preempted run resumes (see splat_gpu.train).
CHECKPOINTS = Path("/vol/checkpoints")


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
    max_containers=MODEL_GPUS,
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


@app.function(
    image=splat_image,
    gpu=["L40S", "A100-40GB"],  # Modal falls back to an A100 when no L40S is free.
    volumes={"/vol": vol},
    timeout=3600,
    max_containers=SPLAT_GPUS,
    scaledown_window=60,
)
def run_splat(model: str, task: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Train and split one splat, or remove objects from one (fill B).

    Both share this function, so they share its GPU. The time charged includes
    loading and evaluation.
    """
    import removal_gpu
    import splat_gpu

    started = time.time()
    vol.reload()
    splat_gpu.load_cached_kernels()
    try:
        if task == "twin_splat" and model.startswith("gsplat@"):
            output = splat_gpu.train(
                payload,
                _store(),
                steps=int(payload.get("steps", 15000)),
                checkpoints=CHECKPOINTS,
                persist=vol.commit,
            )
        elif task == "twin_remove" and model.startswith("big-lama@"):
            output = removal_gpu.remove(
                payload,
                _store(),
                lama_sha256=model.split("@", 1)[1],
                steps=int(payload.get("steps", 5000)),
            )
        else:
            return {"error": f"unknown splat task {task} for {model}"}
    except splat_gpu.InputError as error:
        return {"error": str(error)}
    splat_gpu.save_compiled_kernels()
    vol.commit()
    return {"output": output, "gpu_seconds": round(time.time() - started, 3)}


def _ply_count(path: Path) -> int:
    with path.open("rb") as file:
        for line in file:
            if line.startswith(b"element vertex"):
                return int(line.split()[-1])
            if line.startswith(b"end_header"):
                break
    return 0


def _splat_transform(args: list[str]) -> tuple[bool, str]:
    import subprocess

    done = subprocess.run(  # noqa: S603 (fixed tool, arguments built here)
        ["splat-transform", "-w", "-g", "cpu", *args],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    )
    return done.returncode == 0, (done.stderr or done.stdout)[-600:]


@app.function(
    image=compress_image,
    volumes={"/vol": vol},
    cpu=16,
    memory=32768,
    timeout=3600,
    max_containers=1,
)
def compress_splat(payload: dict[str, Any]) -> dict[str, Any]:
    """Decimate a splat to each Gaussian budget and save it as colour-only SOG.

    Adaptive (mass-preserving) decimation needs WebGPU above about 2M Gaussians;
    on CPU it falls back to plain decimation, which the spike found as good.
    """
    import tempfile

    started = time.time()
    vol.reload()
    store = _store()
    if not store.has_blob(payload["splat"]):
        return {"error": "splat is not in the store"}
    work = Path(tempfile.mkdtemp())
    full = work / "full.ply"
    full.write_bytes(store.read_blob(payload["splat"]))
    source = _ply_count(full)
    variants = []
    for budget in payload["budgets"]:
        t0 = time.time()
        ply, sog = work / f"{budget}.ply", work / f"{budget}.sog"
        method = None
        if budget >= source:
            ply, method = full, "none"
        else:
            for flag in ("--decimate-adaptive", "--decimate"):
                ok, _ = _splat_transform([str(full), flag, str(budget), str(ply)])
                if ok:
                    method = flag.lstrip("-")
                    break
        if method is None:
            return {"error": f"splat-transform could not decimate to {budget}"}
        ok, err = _splat_transform([str(ply), "-H", "0", str(sog)])
        if not ok:
            return {"error": f"splat-transform could not write SOG: {err}"}
        variants.append(
            {
                "budget": budget,
                "gaussians": _ply_count(ply),
                "sog": store.put_blob(sog.read_bytes()),
                "bytes": sog.stat().st_size,
                "decimate_method": method,
                "seconds": round(time.time() - t0, 1),
            }
        )
    vol.commit()
    return {
        "source_gaussians": source,
        "variants": variants,
        "cpu_seconds": round(time.time() - started, 1),
    }


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


def volume_invoke(task: str, function: Any = None):
    """Gateway invoke for a CPU orchestrator: share blobs with the GPU function.

    The volume is committed before the call so the GPU sees the inputs, and
    reloaded after it so the orchestrator sees what the GPU wrote.
    """

    async def invoke(model: str, payload: Any) -> Any:
        vol.commit()
        reply = await (function or run_model).remote.aio(model, task, dict(payload))
        vol.reload()
        return reply

    return invoke


def _y_up(up: Any) -> Any:
    """Rotation that turns a dataset's up vector into +y, as in an AR session's world."""
    import numpy as np

    a = np.asarray(up, dtype=np.float64) / np.linalg.norm(up)
    b = np.array([0.0, 1.0, 0.0])
    v, c = np.cross(a, b), float(a @ b)
    vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + vx + vx @ vx / (1.0 + c)


def _arkit_manifest(store: Any, scene: str, keyframes: int, y_up: bool = False) -> dict[str, Any]:
    """A frames manifest from an ARKitScenes room on the spike volume (smoke runs only).

    With `y_up`, the room is turned into an AR session's world (y up), as a phone
    capture package delivers it.
    """
    import json

    import numpy as np

    cams = json.loads(Path(f"/vol/scenes/{scene}/cameras.json").read_text())
    up_axis = int(np.argmax(np.abs(cams["up"])))
    turn = np.eye(4)
    if y_up:
        turn[:3, :3] = _y_up(cams["up"])
        up_axis = 1
    picks = np.linspace(0, len(cams["frames"]) - 1, keyframes).round().astype(int)
    frames = []
    for i in picks:
        f = cams["frames"][int(i)]
        base = Path(f"/vol/scenes/{scene}")
        frames.append(
            {
                "keyframe_id": f"kf{int(i):04d}",
                "image": store.put_blob((base / f["file"]).read_bytes()),
                "width": f["w"],
                "height": f["h"],
                "intrinsics": f["K"],
                "c2w": (turn @ np.asarray(f["c2w"])).tolist(),
                "depth": store.put_blob((base / f["depth"]).read_bytes()),
            }
        )
    return {"up_axis": up_axis, "depth_source": "lidar", "frames": frames}


@app.function(
    image=cpu_image, volumes={"/work": vol, "/vol": spike_vol}, cpu=4, memory=8192, timeout=3600
)
def objects_smoke_cpu(scene: str, keyframes: int) -> dict[str, Any]:
    """Run the objects step on one ARKitScenes room and score it against its boxes."""
    import asyncio
    import json
    import math

    from twin_gpu.objects import gt_boxes, gt_seen

    from sajao_gateway import InMemorySpendLedger, ModelGateway, SpendCaps
    from sajao_workers.models import detect_chain, segment_chain
    from sajao_workers.steps import LocalArtifactStore, StepRunner
    from sajao_workers.twin.objects_step import objects_step
    from twin_risk.geometry import UprightBox
    from twin_risk.metrics import LabelledBox, summarise

    store = LocalArtifactStore(Path("/work/artifacts"))
    manifest = _arkit_manifest(store, scene, keyframes)
    up_axis = manifest["up_axis"]
    caps = SpendCaps(per_user_daily_micro_inr=10**9, global_daily_micro_inr=10**9)
    ledger = InMemorySpendLedger(caps)
    step = objects_step(
        ModelGateway(detect_chain(volume_invoke("twin_detect")), ledger=ledger),
        ModelGateway(segment_chain(volume_invoke("twin_segment")), ledger=ledger),
    )
    result = asyncio.run(
        StepRunner(store, max_attempts=1).run(
            step, {"frames": store.put_blob(json.dumps(manifest).encode())}, {}
        )
    )
    vol.commit()
    objects = json.loads(store.read_blob(result.outputs["objects"]))
    preds = [
        LabelledBox(
            o["category"],
            UprightBox(
                tuple(o["box"]["center"]),
                o["box"]["length"]["value_m"],
                o["box"]["width"]["value_m"],
                o["box"]["height"]["value_m"],
                math.radians(o["box"]["yaw_deg"]),
                up_axis,
            ),
        )
        for o in objects
    ]
    gts = gt_boxes(scene, up_axis)
    seen = [g for g, ok in zip(gts, gt_seen(scene, gts), strict=True) if ok]
    return {
        "scene": scene,
        "keyframes": keyframes,
        "objects": len(objects),
        "cached": result.cached,
        "meta": dict(result.meta),
        "charged_micro_inr": result.cost_micro_inr,
        "metrics_seen": summarise(preds, seen),
        "all": [
            {k: o[k] for k in ("category", "frames", "confidence")}
            | {"size_m": [o["box"][s]["value_m"] for s in ("length", "width", "height")]}
            | {"center": o["box"]["center"]}
            for o in objects
        ],
    }


@app.local_entrypoint()
def objects_smoke(scene: str = "arkit_living_47331265", keyframes: int = 120) -> None:
    import json

    print(json.dumps(objects_smoke_cpu.remote(scene, keyframes), indent=1))


@app.function(
    image=cpu_image, volumes={"/work": vol, "/vol": spike_vol}, cpu=4, memory=8192, timeout=7200
)
def splat_smoke_cpu(scene: str, keyframes: int) -> dict[str, Any]:
    """Objects then splat on one ARKitScenes room, through the gateways and durable steps."""
    import asyncio
    import json

    from sajao_gateway import InMemorySpendLedger, ModelGateway, SpendCaps
    from sajao_workers.models import detect_chain, segment_chain, splat_chain
    from sajao_workers.steps import LocalArtifactStore, StepRunner
    from sajao_workers.twin.objects_step import objects_step
    from sajao_workers.twin.splat_step import splat_step

    store = LocalArtifactStore(Path("/work/artifacts"))
    manifest = _arkit_manifest(store, scene, keyframes)
    caps = SpendCaps(per_user_daily_micro_inr=10**9, global_daily_micro_inr=10**9)
    ledger = InMemorySpendLedger(caps)
    runner = StepRunner(store, max_attempts=1)
    frames = store.put_blob(json.dumps(manifest).encode())

    async def run() -> dict[str, Any]:
        objects = await runner.run(
            objects_step(
                ModelGateway(detect_chain(volume_invoke("twin_detect")), ledger=ledger),
                ModelGateway(segment_chain(volume_invoke("twin_segment")), ledger=ledger),
            ),
            {"frames": frames},
            {},
        )
        splat = await runner.run(
            splat_step(
                ModelGateway(splat_chain(volume_invoke("twin_splat", run_splat)), ledger=ledger)
            ),
            {"frames": frames, "objects": objects.outputs["objects"]},
            {},
        )
        vol.commit()
        return {
            "scene": scene,
            "keyframes": keyframes,
            "objects": {"cached": objects.cached, **dict(objects.meta)},
            "splat": {"cached": splat.cached, **dict(splat.meta)},
            "splat_bytes": len(store.read_blob(splat.outputs["splat"])),
            "charged_micro_inr": objects.cost_micro_inr + splat.cost_micro_inr,
        }

    return asyncio.run(run())


@app.function(
    image=splat_image,
    gpu=["L40S", "A100-40GB"],
    volumes={"/vol": vol},
    timeout=3600,
    max_containers=1,
)
def resume_test_gpu(frames: str, objects: str, steps: int, interrupt_at: int | None) -> Any:
    """Train with checkpoints, optionally stopping on purpose at `interrupt_at`."""
    import splat_gpu

    vol.reload()
    splat_gpu.load_cached_kernels()
    try:
        out = splat_gpu.train(
            {"frames": frames, "objects": objects},
            _store(),
            steps=steps,
            checkpoints=Path("/vol/checkpoints-test"),
            persist=vol.commit,
            interrupt_at=interrupt_at,
        )
    except splat_gpu.Interrupted as stop:
        return {"interrupted_at": stop.args[0]}
    vol.commit()
    return {k: out.get(k) for k in ("resumed_at_step", "psnr_heldout", "gaussians")}


@app.function(
    image=cpu_image, volumes={"/work": vol, "/vol": spike_vol}, cpu=4, memory=8192, timeout=7200
)
def resume_test_cpu(scene: str, keyframes: int, steps: int, interrupt_at: int) -> dict[str, Any]:
    """A splat run stopped mid-way, then started again: it must resume, not restart."""
    import asyncio
    import json

    from sajao_gateway import InMemorySpendLedger, ModelGateway, SpendCaps
    from sajao_workers.models import detect_chain, segment_chain
    from sajao_workers.steps import LocalArtifactStore, StepRunner
    from sajao_workers.twin.objects_step import objects_step

    store = LocalArtifactStore(Path("/work/artifacts"))
    frames = store.put_blob(json.dumps(_arkit_manifest(store, scene, keyframes)).encode())
    ledger = InMemorySpendLedger(
        SpendCaps(per_user_daily_micro_inr=10**9, global_daily_micro_inr=10**9)
    )
    objects = asyncio.run(
        StepRunner(store, max_attempts=1).run(
            objects_step(
                ModelGateway(detect_chain(volume_invoke("twin_detect")), ledger=ledger),
                ModelGateway(segment_chain(volume_invoke("twin_segment")), ledger=ledger),
            ),
            {"frames": frames},
            {},
        )
    )
    vol.commit()
    first = resume_test_gpu.remote(frames, objects.outputs["objects"], steps, interrupt_at)
    second = resume_test_gpu.remote(frames, objects.outputs["objects"], steps, None)
    return {"first": first, "second": second}


@app.local_entrypoint()
def resume_test(
    scene: str = "arkit_living_47331265",
    keyframes: int = 120,
    steps: int = 6000,
    interrupt_at: int = 5500,
) -> None:
    import json

    print(json.dumps(resume_test_cpu.remote(scene, keyframes, steps, interrupt_at), indent=1))


@app.local_entrypoint()
def splat_smoke(scene: str = "arkit_living_47331265", keyframes: int = 120) -> None:
    import json

    print(json.dumps(splat_smoke_cpu.remote(scene, keyframes), indent=1))


@app.function(
    image=cpu_image, volumes={"/work": vol, "/vol": spike_vol}, cpu=4, memory=8192, timeout=7200
)
def phone_smoke_cpu(scene: str, keyframes: int) -> dict[str, Any]:
    """Objects, splat and phone splats on one room; finished steps are reused."""
    import asyncio
    import json

    from sajao_gateway import InMemorySpendLedger, ModelGateway, SpendCaps
    from sajao_workers.models import detect_chain, segment_chain, splat_chain
    from sajao_workers.steps import LocalArtifactStore, StepRunner
    from sajao_workers.twin.objects_step import objects_step
    from sajao_workers.twin.phone_step import phone_splat_step
    from sajao_workers.twin.splat_step import splat_step

    store = LocalArtifactStore(Path("/work/artifacts"))
    manifest = _arkit_manifest(store, scene, keyframes)
    ledger = InMemorySpendLedger(
        SpendCaps(per_user_daily_micro_inr=10**9, global_daily_micro_inr=10**9)
    )
    runner = StepRunner(store, max_attempts=1)
    frames = store.put_blob(json.dumps(manifest).encode())

    async def compress(payload: Any) -> Any:
        vol.commit()
        reply = await compress_splat.remote.aio(dict(payload))
        vol.reload()
        return reply

    async def run() -> dict[str, Any]:
        objects = await runner.run(
            objects_step(
                ModelGateway(detect_chain(volume_invoke("twin_detect")), ledger=ledger),
                ModelGateway(segment_chain(volume_invoke("twin_segment")), ledger=ledger),
            ),
            {"frames": frames},
            {},
        )
        splat = await runner.run(
            splat_step(
                ModelGateway(splat_chain(volume_invoke("twin_splat", run_splat)), ledger=ledger)
            ),
            {"frames": frames, "objects": objects.outputs["objects"]},
            {},
        )
        phone = await runner.run(phone_splat_step(compress), {"splat": splat.outputs["splat"]}, {})
        return {
            "scene": scene,
            "objects_cached": objects.cached,
            "splat_cached": splat.cached,
            "phone": {"cached": phone.cached, **dict(phone.meta)},
            "phone_charged_micro_inr": phone.cost_micro_inr,
        }

    return asyncio.run(run())


@app.local_entrypoint()
def phone_smoke(scene: str = "arkit_living_47331265", keyframes: int = 120) -> None:
    import json

    print(json.dumps(phone_smoke_cpu.remote(scene, keyframes), indent=1))


@app.function(
    image=cpu_image, volumes={"/work": vol, "/vol": spike_vol}, cpu=8, memory=16384, timeout=7200
)
def twin_smoke_cpu(scene: str, keyframes: int) -> dict[str, Any]:
    """A whole twin from one ARKitScenes room turned into an AR world (y up), end to end."""
    import asyncio
    import json
    import uuid

    from sajao_gateway import InMemorySpendLedger, ModelGateway, SpendCaps
    from sajao_workers.models import detect_chain, segment_chain, splat_chain
    from sajao_workers.steps import LocalArtifactStore, StepRunner
    from sajao_workers.twin.assemble_step import assemble_step
    from sajao_workers.twin.objects_step import objects_step
    from sajao_workers.twin.phone_step import phone_splat_step
    from sajao_workers.twin.splat_step import splat_step

    store = LocalArtifactStore(Path("/work/artifacts"))
    manifest = _arkit_manifest(store, scene, keyframes, y_up=True)
    capture_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"arkitscenes/{scene}"))
    capture = {
        "id": capture_id,
        # ARKitScenes has no compass reading: a declared test heading, not a measurement.
        "compass": {"mean_heading_deg": 0.0, "sample_count": 1},
        "package": {
            "ar": {"tracking": "arkit", "lidar": True, "depth": True},
            "keyframes": [
                {
                    "id": f["keyframe_id"],
                    "image": f"arkitscenes/{scene}/{f['keyframe_id']}.jpg",
                    "captured_at_ms": 500 * i,
                    "sharpness": 1.0,
                }
                for i, f in enumerate(manifest["frames"])
            ],
            "detections": [],
            "sensor_log": f"arkitscenes/{scene}/none.jsonl",
        },
    }
    ledger = InMemorySpendLedger(
        SpendCaps(per_user_daily_micro_inr=10**9, global_daily_micro_inr=10**9)
    )
    runner = StepRunner(store, max_attempts=1)
    frames = store.put_blob(json.dumps(manifest).encode())

    async def compress(payload: Any) -> Any:
        vol.commit()
        reply = await compress_splat.remote.aio(dict(payload))
        vol.reload()
        return reply

    async def run() -> dict[str, Any]:
        objects = await runner.run(
            objects_step(
                ModelGateway(detect_chain(volume_invoke("twin_detect")), ledger=ledger),
                ModelGateway(segment_chain(volume_invoke("twin_segment")), ledger=ledger),
            ),
            {"frames": frames},
            {},
        )
        splat = await runner.run(
            splat_step(
                ModelGateway(splat_chain(volume_invoke("twin_splat", run_splat)), ledger=ledger)
            ),
            {"frames": frames, "objects": objects.outputs["objects"]},
            {},
        )
        phone = await runner.run(phone_splat_step(compress), {"splat": splat.outputs["splat"]}, {})
        twin = await runner.run(
            assemble_step(),
            {
                "capture": store.put_blob(json.dumps(capture).encode()),
                "frames": frames,
                "objects": objects.outputs["objects"],
                "splat": splat.outputs["splat"],
                "phone": store.put_blob(json.dumps(dict(phone.meta)).encode()),
                **phone.outputs,
            },
            {
                "twin_id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"twin/{capture_id}")),
                "version": 1,
                "created_at": "2026-11-16T00:00:00Z",
            },
        )
        vol.commit()
        doc = json.loads(store.read_blob(twin.outputs["twin"]))
        return {
            "scene": scene,
            "cached": {
                "objects": objects.cached,
                "splat": splat.cached,
                "phone": phone.cached,
                "twin": twin.cached,
            },
            "twin": dict(twin.meta),
            "splat": {k: splat.meta.get(k) for k in ("psnr_heldout", "gaussians", "gpu")},
            "phone_mb": {k: round(v["bytes"] / 1e6, 2) for k, v in phone.meta["variants"].items()},
            "twin_bytes": len(store.read_blob(twin.outputs["twin"])),
            "first_object": doc["objects"][0] if doc["objects"] else None,
            "charged_micro_inr": objects.cost_micro_inr
            + splat.cost_micro_inr
            + phone.cost_micro_inr,
        }

    return asyncio.run(run())


def _save(path: str, data: bytes) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(data)


@app.function(
    image=cpu_image, volumes={"/work": vol, "/vol": spike_vol}, cpu=8, memory=16384, timeout=7200
)
def removal_smoke_cpu(scene: str, keyframes: int, category: str) -> dict[str, Any]:
    """Remove the most-seen object of `category` from one ARKitScenes room's twin.

    The objects and splat steps are the twin smoke's, so their stored results are reused.
    """
    import asyncio
    import json

    from sajao_gateway import InMemorySpendLedger, ModelGateway, SpendCaps
    from sajao_workers.models import detect_chain, removal_chain, segment_chain, splat_chain
    from sajao_workers.steps import LocalArtifactStore, StepRunner
    from sajao_workers.twin.objects_step import objects_step
    from sajao_workers.twin.removal_step import removal_step
    from sajao_workers.twin.splat_step import splat_step

    store = LocalArtifactStore(Path("/work/artifacts"))
    frames = store.put_blob(
        json.dumps(_arkit_manifest(store, scene, keyframes, y_up=True)).encode()
    )
    ledger = InMemorySpendLedger(
        SpendCaps(per_user_daily_micro_inr=10**9, global_daily_micro_inr=10**9)
    )
    runner = StepRunner(store, max_attempts=1)

    async def run() -> dict[str, Any]:
        objects = await runner.run(
            objects_step(
                ModelGateway(detect_chain(volume_invoke("twin_detect")), ledger=ledger),
                ModelGateway(segment_chain(volume_invoke("twin_segment")), ledger=ledger),
            ),
            {"frames": frames},
            {},
        )
        splat = await runner.run(
            splat_step(
                ModelGateway(splat_chain(volume_invoke("twin_splat", run_splat)), ledger=ledger)
            ),
            {"frames": frames, "objects": objects.outputs["objects"]},
            {},
        )
        found = json.loads(store.read_blob(objects.outputs["objects"]))
        picks = [i for i, o in enumerate(found, start=1) if o["category"] == category]
        if not picks:
            return {"scene": scene, "error": f"no {category} found"}
        index = max(picks, key=lambda i: found[i - 1]["frames"])
        removed = await runner.run(
            removal_step(
                ModelGateway(removal_chain(volume_invoke("twin_remove", run_splat)), ledger=ledger)
            ),
            {
                "frames": frames,
                "objects": objects.outputs["objects"],
                **{k: splat.outputs[k] for k in ("splat", "labels", "cameras")},
            },
            {"object_ids": [f"o{index}"], "preview": True},
        )
        preview = f"/work/previews/{scene}_o{index}_{category}.jpg"
        await asyncio.to_thread(_save, preview, store.read_blob(removed.outputs["preview"]))
        vol.commit()
        return {
            "scene": scene,
            "object": f"o{index}",
            "category": category,
            "box": found[index - 1]["box"],
            "cached": removed.cached,
            "removal": dict(removed.meta),
            "preview": preview,
            "charged_micro_inr": removed.cost_micro_inr,
        }

    return asyncio.run(run())


@app.local_entrypoint()
def removal_smoke(
    scene: str = "arkit_living_47331265", keyframes: int = 120, category: str = "sofa"
) -> None:
    import json

    print(json.dumps(removal_smoke_cpu.remote(scene, keyframes, category), indent=1))


@app.local_entrypoint()
def twin_smoke(scene: str = "arkit_living_47331265", keyframes: int = 120) -> None:
    import json

    print(json.dumps(twin_smoke_cpu.remote(scene, keyframes), indent=1))
