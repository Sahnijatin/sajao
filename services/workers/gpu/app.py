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

# Code revisions of the depth models (weights are pinned in sajao_workers.models).
MOGE_REF = "74fbce054ebed49800de42d0ad0e83495065719a"
DA3_REF = "3d835ec1a5802d64a8b8b15f817a1ab54809bfe4"

# Detection, segmentation and depth share one image (torch 2.8, as MoGe-3 and DA3
# need), so they share the model function and its GPUs.
gpu_image = (
    modal.Image.from_registry("nvidia/cuda:12.8.1-cudnn-devel-ubuntu22.04", add_python="3.11")
    .apt_install("git", "libgl1", "libglib2.0-0", "build-essential")
    .pip_install("torch==2.8.0", "torchvision==0.23.0", "xformers==0.0.32.post2")
    .pip_install(
        "numpy==2.1.3",
        "pillow==11.0.0",
        "opencv-python-headless==4.10.0.84",
        "transformers==4.57.1",
        "ultralytics==8.4.214",
        "git+https://github.com/ultralytics/CLIP.git",
    )
    # MoGe and DA3 declare demo and export packages that clash with the detectors' stack
    # (DA3 wants numpy<2; MoGe pulls a huggingface-hub that transformers rejects). Both are
    # installed without their lists, with what inference imports; the build checks that.
    .pip_install(
        f"moge @ git+https://github.com/microsoft/MoGe@{MOGE_REF}",
        f"depth-anything-3 @ git+https://github.com/ByteDance-Seed/Depth-Anything-3@{DA3_REF}",
        extra_options="--no-deps",
    )
    # Export-only imports of DA3 (two of them GPL-3.0) are stubbed: see da3_stubs/README.md.
    .add_local_dir(HERE / "da3_stubs", "/opt/da3_stubs", copy=True)
    .env({"PYTHONPATH": "/opt/da3_stubs"})
    .pip_install(
        # MoGe's own pins (git commits from its pyproject).
        "utils3d_moge @ git+https://github.com/EasternJournalist/utils3d-moge.git@62f09d58509485564e24d5d9f6aac9ee9ebc0c37",
        "pipeline @ git+https://github.com/EasternJournalist/pipeline.git@1c511390d90226c00c101f34b84df26a0f8789b4",
        "flex-gemm @ git+https://github.com/JeffreyXiang/FlexGEMM.git@b2fadb29d41846c7981ade6801ffc689fae119cf",
        "scipy==1.17.1",
        "click==8.5.1",
        "matplotlib==3.10.7",
        "tqdm==4.67.1",
        "addict==2.4.0",
        "einops==0.8.1",
        "omegaconf==2.3.0",
        "safetensors==0.6.2",
        "imageio==2.37.0",
        "trimesh==4.11.0",
        "e3nn==0.5.8",
        "typer==0.19.2",
        "pillow_heif==1.1.1",
    )
    .run_commands(
        # MoGe's FlexGEMM asks the GPU its name on import, so the build (no GPU) only
        # checks MoGe is present; the depth smoke loads it on a GPU.
        "python -c 'import importlib.util, numpy, transformers;"
        " from depth_anything_3.api import DepthAnything3; from transformers import Sam2Model;"
        ' assert importlib.util.find_spec("moge.model.v3");'
        " print(numpy.__version__, transformers.__version__)'"
    )
    .env({"HF_HOME": "/vol/hf", "HF_HUB_DISABLE_XET": "1", "PYTHONUNBUFFERED": "1"})
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
    .add_local_file(HERE / "review_gpu.py", "/root/review_gpu.py")
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
    # Vision models for the room inventory (Gemini on Vertex AI, Claude).
    .pip_install("httpx==0.28.1", "google-auth[requests]==2.62.2", "anthropic==2.8.0")
    .pip_install("imageio==2.37.0", "imageio-ffmpeg==0.6.0")  # review videos
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
# Credentials for the inventory's vision models: GCP_SA_KEY and GCP_PROJECT_ID; ANTHROPIC_API_KEY.
VISION_SECRETS = [modal.Secret.from_name("gcp"), modal.Secret.from_name("anthropic-secret")]
# Splat training state, so a preempted run resumes (see splat_gpu.train).
CHECKPOINTS = Path("/vol/checkpoints")


GDINO_PROMPTS_PER_PASS = 16


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
            Owlv2ForObjectDetection,
            Owlv2Processor,
            Sam2Model,
            Sam2Processor,
        )

        name, revision = _split(model)
        if kind == "detect" and name.startswith("google/owlv2"):
            processor = Owlv2Processor.from_pretrained(name, revision=revision)
            network = Owlv2ForObjectDetection.from_pretrained(name, revision=revision)
        elif kind == "detect":
            processor = AutoProcessor.from_pretrained(name, revision=revision)
            network = AutoModelForZeroShotObjectDetection.from_pretrained(name, revision=revision)
        else:
            processor = Sam2Processor.from_pretrained(name, revision=revision)
            network = Sam2Model.from_pretrained(name, revision=revision)
        _loaded[model] = (processor, network.cuda().eval())
    loaded: tuple[Any, Any] = _loaded[model]
    return loaded


def detect(model: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Boxes, labels and scores per frame. Labels outside the vocabulary are dropped.

    Detectors are prompted with `prompts` (a description per class, same order as
    `vocabulary`) and report each detection under its class name. `min_score`
    overrides the detector's score threshold (benchmarks, and the retry for listed
    items not placed).
    """
    import torch
    import torchvision
    from PIL import Image

    vocabulary = list(payload["vocabulary"])
    prompts = list(payload.get("prompts") or vocabulary)
    if len(prompts) != len(vocabulary):
        raise InputError("one prompt per vocabulary entry")
    by_prompt = {p.lower().strip(): name for p, name in zip(prompts, vocabulary, strict=True)}
    frames = []
    for image in payload["images"]:
        rgb = _rgb(image["image"])
        height, width = rgb.shape[:2]
        pil = Image.fromarray(rgb)
        if model.startswith("yoloe"):
            conf = float(payload.get("min_score", 0.25))
            found = _yoloe(model, prompts).predict(pil, conf=conf, verbose=False)[0]
            boxes, scores = found.boxes.xyxy.float(), found.boxes.conf.float()
            labels = [vocabulary[int(c)] for c in found.boxes.cls.tolist()]
        elif model.startswith("IDEA-Research/grounding-dino"):
            processor, network = _hf(model, "detect")
            # Its text encoder reads at most 256 tokens: a room's inventory goes in chunks.
            parts = []
            for start in range(0, len(prompts), GDINO_PROMPTS_PER_PASS):
                chunk = prompts[start : start + GDINO_PROMPTS_PER_PASS]
                inputs = processor(images=pil, text=". ".join(chunk) + ".", return_tensors="pt")
                with torch.no_grad():
                    out = network(**inputs.to("cuda"))
                parts.append(
                    processor.post_process_grounded_object_detection(
                        out,
                        inputs.input_ids,
                        threshold=float(payload.get("min_score", 0.30)),
                        text_threshold=0.25,
                        target_sizes=[(height, width)],
                    )[0]
                )
            boxes = torch.cat([r["boxes"].float() for r in parts])
            scores = torch.cat([r["scores"].float() for r in parts])
            labels = [
                by_prompt.get(str(x).lower().strip(), "") for r in parts for x in r["text_labels"]
            ]
        elif model.startswith("google/owlv2"):
            processor, network = _hf(model, "detect")
            inputs = processor(text=[prompts], images=pil, return_tensors="pt")
            with torch.no_grad():
                out = network(**inputs.to("cuda"))
            # OWLv2 pads the image to a square: boxes are scaled by the longer side.
            side = max(height, width)
            result = processor.post_process_object_detection(
                out, threshold=float(payload.get("min_score", 0.2)), target_sizes=[(side, side)]
            )[0]
            boxes, scores = result["boxes"].float(), result["scores"].float()
            labels = [vocabulary[int(i)] for i in result["labels"].tolist()]
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


def _depth_model(model: str) -> Any:
    if model not in _loaded:
        name, revision = _split(model)
        if name == "Ruicheng/moge-3-vitl":
            from huggingface_hub import hf_hub_download
            from moge.model.v3 import MoGeModel

            weights = hf_hub_download(name, "model.pt", revision=revision)
            _loaded[model] = MoGeModel.from_pretrained(weights).to("cuda").eval()
        elif name == "depth-anything/DA3METRIC-LARGE":
            from depth_anything_3.api import DepthAnything3

            _loaded[model] = DepthAnything3.from_pretrained(name, revision=revision)
            _loaded[model] = _loaded[model].to("cuda").eval()
        else:
            raise InputError(f"unknown depth model {model}")
    return _loaded[model]


def depth(model: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Metric depth per frame at the image size, stored as a 16-bit PNG in millimetres.

    MoGe-3 is given the field of view from the AR intrinsics; DA3 Metric's output
    becomes metres as focal length (pixels, at its processed size) times output / 300.
    """
    import math

    import cv2
    import numpy as np
    import torch

    network = _depth_model(model)
    store = _store()
    frames = []
    for frame in payload["frames"]:
        rgb = _rgb(frame["image"])
        h, w = rgb.shape[:2]
        k = np.asarray(frame["intrinsics"], dtype=np.float64)
        if model.startswith("Ruicheng/moge"):
            fov_x = math.degrees(2 * math.atan(w / (2 * k[0, 0])))
            image = torch.tensor(rgb / 255, dtype=torch.float32, device="cuda").permute(2, 0, 1)
            with torch.no_grad():
                out = network.infer(image, fov_x=fov_x)
            metres = out["depth"].float().cpu().numpy()
            metres = np.where(out["mask"].cpu().numpy().astype(bool), metres, 0.0)
        else:
            with torch.no_grad():
                raw = network.inference([rgb]).depth[0]
            ph, pw = raw.shape
            focal = (k[0, 0] * pw / w + k[1, 1] * ph / h) / 2
            metres = cv2.resize(focal * raw / 300.0, (w, h), interpolation=cv2.INTER_LINEAR)
        metres = np.where(np.isfinite(metres) & (metres > 0) & (metres < 65.0), metres, 0.0)
        valid = metres > 0
        png = cv2.imencode(".png", np.round(metres * 1000).astype(np.uint16))[1].tobytes()
        frames.append(
            {
                "image": frame["image"],
                "depth": store.put_blob(png),
                "coverage": round(float(valid.mean()), 4),
                "median_m": round(float(np.median(metres[valid])), 3) if valid.any() else 0.0,
            }
        )
    return {"frames": frames}


HANDLERS = {"twin_detect": detect, "twin_segment": segment, "twin_depth": depth}


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
        elif task == "twin_review" and model.startswith("gsplat@"):
            import review_gpu

            output = review_gpu.review(payload, _store())
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
def objects_smoke_cpu(
    scene: str, keyframes: int, depth: str = "lidar", detectors: str = ""
) -> dict[str, Any]:
    """Run the objects step on one ARKitScenes room and score it against its boxes.

    With `depth` "model", LiDAR is withheld: the depth step estimates depth first
    (as on a phone without LiDAR), and its error against LiDAR is reported too.
    "da3" does the same with the fallback model alone.
    """
    import asyncio
    import json
    import math

    import numpy as np
    from twin_gpu.objects import gt_boxes, gt_seen

    from sajao_gateway import InMemorySpendLedger, ModelGateway, SpendCaps
    from sajao_workers.models import depth_chain, detect_chain, detector_order, segment_chain
    from sajao_workers.steps import LocalArtifactStore, StepRunner
    from sajao_workers.twin.depth_step import depth_step
    from sajao_workers.twin.objects import decode_depth_mm, depth_at
    from sajao_workers.twin.objects_step import objects_step
    from twin_risk.geometry import UprightBox
    from twin_risk.metrics import LabelledBox, summarise

    chosen = {"SAJAO_DETECTORS": detectors} if detectors else {}
    store = LocalArtifactStore(Path("/work/artifacts"))
    manifest = _arkit_manifest(store, scene, keyframes)
    up_axis = manifest["up_axis"]
    caps = SpendCaps(per_user_daily_micro_inr=10**9, global_daily_micro_inr=10**9)
    ledger = InMemorySpendLedger(caps)
    step = objects_step(
        ModelGateway(
            detect_chain(volume_invoke("twin_detect"), order=detector_order(chosen)),
            ledger=ledger,
        ),
        ModelGateway(segment_chain(volume_invoke("twin_segment")), ledger=ledger),
    )
    runner = StepRunner(store, max_attempts=1)
    frames = store.put_blob(json.dumps(manifest).encode())
    depth_report: dict[str, Any] = {}
    if depth in ("model", "da3"):
        chain = depth_chain(volume_invoke("twin_depth"))
        if depth == "da3":
            chain = chain[1:]
        lidar = {f["keyframe_id"]: f["depth"] for f in manifest["frames"]}
        withheld = {
            **manifest,
            "depth_source": "image",
            "frames": [{**f, "depth": None} for f in manifest["frames"]],
        }
        estimated = asyncio.run(
            runner.run(
                depth_step(ModelGateway(chain, ledger=ledger)),
                {"frames": store.put_blob(json.dumps(withheld).encode())},
                # The step's key does not name the chain: keep the DA3-only run apart.
                {"smoke_chain": depth},
            )
        )
        frames = estimated.outputs["frames"]
        absrel = []
        for f in json.loads(store.read_blob(frames))["frames"]:
            truth = decode_depth_mm(store.read_blob(lidar[f["keyframe_id"]]))
            guess = depth_at(decode_depth_mm(store.read_blob(f["depth"])), truth.shape)
            ok = (truth > 0) & (guess > 0)
            if ok.sum() >= 100:  # some frames have almost no confident LiDAR
                absrel.append(float(np.median(np.abs(guess[ok] - truth[ok]) / truth[ok])))
        depth_report = {
            **dict(estimated.meta),
            "median_absrel_vs_lidar": round(float(np.median(absrel)), 3) if absrel else None,
            "frames_scored": len(absrel),
            "charged_micro_inr": estimated.cost_micro_inr,
        }
    # The step's key does not name the detector chain: keep other chains' runs apart.
    result = asyncio.run(runner.run(step, {"frames": frames}, chosen))
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
        "depth": depth_report or "lidar",
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


@app.function(
    image=cpu_image, volumes={"/work": vol, "/vol": spike_vol}, cpu=4, memory=8192, timeout=3600
)
def detector_bench_cpu(labels: dict[str, str]) -> dict[str, Any]:
    """Each detector on the hand-checked Indian-object photos (file -> class).

    Image-level scores: a photo counts as found when the detector reports its class
    (strict) or a class in the same group (lenient, e.g. almirah reported as
    wardrobe); the other Indian classes it reports are counted as confusions.
    """
    import json
    import time as clock

    from PIL import Image

    from sajao_workers.models import (
        _DETECTOR_MODELS,
        DETECTORS,
        INDIAN_VOCABULARY,
        VOCABULARY,
        prompts_for,
    )
    from sajao_workers.steps import LocalArtifactStore
    from sajao_workers.twin.fusion import GROUPS

    store = LocalArtifactStore(Path("/work/artifacts"))
    root = Path("/vol/indian/openverse")
    images = []
    for name in sorted(labels):
        data = (root / name).read_bytes()
        width, height = Image.open(root / name).size
        images.append({"image": store.put_blob(data), "width": width, "height": height})
    vol.commit()
    payload = {
        "images": images,
        "vocabulary": list(VOCABULARY),
        "prompts": prompts_for(VOCABULARY),
    }
    group = {c: GROUPS.get(c, c) for c in VOCABULARY}
    # Frames of US homes from ARKitScenes, where these classes should not appear.
    absent = {"almirah", "diwan", "puja unit", "geyser", "air cooler", "jhoola", "floor seating"}
    scenes = []
    for scene in ("arkit_living_47331265", "arkit_bedroom_47430034"):
        scenes += [
            {"image": f["image"], "width": f["width"], "height": f["height"]}
            for f in _arkit_manifest(store, scene, 40)["frames"]
        ]
    vol.commit()
    runs = [(d, d, None) for d in DETECTORS] + [("yoloe at 0.10", "yoloe", 0.10)]
    out: dict[str, Any] = {"photos": len(images), "us_home_frames": len(scenes)}
    for key, detector, min_score in runs:
        started = clock.time()
        extra = {} if min_score is None else {"min_score": min_score}
        reply = run_model.remote(_DETECTOR_MODELS[detector], "twin_detect", {**payload, **extra})
        if "error" in reply:
            out[key] = {"error": reply["error"]}
            continue
        per_class: dict[str, dict[str, int]] = {}
        for name, frame in zip(sorted(labels), reply["output"]["frames"], strict=True):
            truth = labels[name]
            found = {d["label"] for d in frame["detections"]}
            empty = {"photos": 0, "strict": 0, "lenient": 0, "confused": 0}
            row = per_class.setdefault(truth, empty)
            row["photos"] += 1
            row["strict"] += truth in found
            row["lenient"] += truth in found or any(group[f] == group[truth] for f in found)
            row["confused"] += any(f != truth and f in INDIAN_VOCABULARY for f in found)
        n = sum(r["photos"] for r in per_class.values())
        scene_reply = run_model.remote(
            _DETECTOR_MODELS[detector],
            "twin_detect",
            {**payload, **extra, "images": scenes},
        )
        alarms: dict[str, int] = {}
        for frame in scene_reply.get("output", {}).get("frames", []):
            for label in {d["label"] for d in frame["detections"]} & absent:
                alarms[label] = alarms.get(label, 0) + 1
        fired = sum(
            1
            for frame in scene_reply.get("output", {}).get("frames", [])
            if {d["label"] for d in frame["detections"]} & absent
        )
        out[key] = {
            "strict_recall": round(sum(r["strict"] for r in per_class.values()) / n, 3),
            "lenient_recall": round(sum(r["lenient"] for r in per_class.values()) / n, 3),
            "confusion_rate": round(sum(r["confused"] for r in per_class.values()) / n, 3),
            "false_alarm_frames": round(fired / len(scenes), 3),
            "false_alarms": alarms,
            "gpu_seconds": reply["gpu_seconds"] + scene_reply.get("gpu_seconds", 0),
            "wall_seconds": round(clock.time() - started, 1),
            "per_class": per_class,
        }
        print(json.dumps({key: {k: v for k, v in out[key].items() if k != "per_class"}}))
    return out


@app.local_entrypoint()
def detector_bench(labels: str = "eval/twin-indian/labels.json") -> None:
    import json

    result = detector_bench_cpu.remote(json.loads(Path(labels).read_text()))
    Path("eval/twin-indian/results.json").write_text(json.dumps(result, indent=1) + "\n")
    summary = {
        k: {m: n for m, n in v.items() if m != "per_class"} if isinstance(v, dict) else v
        for k, v in result.items()
    }
    print(json.dumps(summary, indent=1))


@app.local_entrypoint()
def objects_smoke(
    scene: str = "arkit_living_47331265",
    keyframes: int = 120,
    depth: str = "lidar",
    detectors: str = "",
) -> None:
    import json

    print(json.dumps(objects_smoke_cpu.remote(scene, keyframes, depth, detectors), indent=1))


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


def _arkit_capture(scene: str, manifest: dict[str, Any]) -> dict[str, Any]:
    """A Capture record for an ARKitScenes room (smoke runs only)."""
    import uuid

    return {
        "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"arkitscenes/{scene}")),
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


async def _compress(payload: Any) -> Any:
    vol.commit()
    reply = await compress_splat.remote.aio(dict(payload))
    vol.reload()
    return reply


def _inventory_gateways(ledger: Any) -> tuple[Any, Any]:
    """The lister (Gemini on Vertex AI, Flash then Flash-Lite) and the cross-check (Claude)."""
    import os

    from sajao_gateway import ModelGateway
    from sajao_workers.vision import (
        CLAUDE_OPUS,
        GEMINI_3_FLASH,
        GEMINI_35_FLASH_LITE,
        ClaudeVision,
        GoogleTokens,
        VertexGeminiVision,
    )

    tokens = GoogleTokens()
    project = os.environ["GCP_PROJECT_ID"]
    lister = ModelGateway(
        [
            VertexGeminiVision("gemini-flash", GEMINI_3_FLASH, project=project, tokens=tokens),
            VertexGeminiVision(
                "gemini-flash-lite", GEMINI_35_FLASH_LITE, project=project, tokens=tokens
            ),
        ],
        ledger=ledger,
    )
    checker = ModelGateway([ClaudeVision("claude", CLAUDE_OPUS)], ledger=ledger)
    return lister, checker


async def _objects(runner: Any, ledger: Any, frames: str, detectors: str = "") -> tuple[Any, Any]:
    """The inventory, then the objects found from it (durable steps)."""
    from sajao_gateway import ModelGateway
    from sajao_workers.models import detect_chain, detector_order, segment_chain
    from sajao_workers.twin.inventory_step import inventory_step
    from sajao_workers.twin.objects_step import objects_step

    inventory = await runner.run(
        inventory_step(*_inventory_gateways(ledger)), {"frames": frames}, {}
    )
    chosen = {"SAJAO_DETECTORS": detectors} if detectors else {}
    objects = await runner.run(
        objects_step(
            ModelGateway(
                detect_chain(volume_invoke("twin_detect"), order=detector_order(chosen)),
                ledger=ledger,
            ),
            ModelGateway(segment_chain(volume_invoke("twin_segment")), ledger=ledger),
        ),
        {"frames": frames, "inventory": inventory.outputs["inventory"]},
        # The step's key does not name the detector chain: keep other chains' runs apart.
        chosen,
    )
    return inventory, objects


async def _build_twin(
    store: Any, runner: Any, ledger: Any, capture: dict[str, Any], manifest: dict[str, Any]
) -> dict[str, Any]:
    """Inventory, objects, splat, phone splats and the twin, each a durable step (stored
    results reused)."""
    import json
    import uuid

    from sajao_gateway import ModelGateway
    from sajao_workers.models import splat_chain
    from sajao_workers.twin.assemble_step import assemble_step
    from sajao_workers.twin.phone_step import phone_splat_step
    from sajao_workers.twin.splat_step import splat_step

    frames = store.put_blob(json.dumps(manifest).encode())
    inventory, objects = await _objects(runner, ledger, frames)
    splat = await runner.run(
        splat_step(
            ModelGateway(splat_chain(volume_invoke("twin_splat", run_splat)), ledger=ledger)
        ),
        {"frames": frames, "objects": objects.outputs["objects"]},
        {},
    )
    phone = await runner.run(phone_splat_step(_compress), {"splat": splat.outputs["splat"]}, {})
    twin = await runner.run(
        assemble_step(),
        {
            "capture": store.put_blob(json.dumps(capture).encode()),
            "frames": frames,
            "objects": objects.outputs["objects"],
            "openings": objects.outputs["openings"],
            "built_ins": objects.outputs["built_ins"],
            "inventory": objects.outputs["inventory"],
            "splat": splat.outputs["splat"],
            "phone": store.put_blob(json.dumps(dict(phone.meta)).encode()),
            **phone.outputs,
        },
        {
            "twin_id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"twin/{capture['id']}")),
            "version": 1,
            "created_at": capture.get("created_at", "2026-11-16T00:00:00Z"),
        },
    )
    vol.commit()
    return {
        "frames": frames,
        "inventory": inventory,
        "objects": objects,
        "splat": splat,
        "phone": phone,
        "twin": twin,
    }


def _ledger() -> Any:
    from sajao_gateway import InMemorySpendLedger, SpendCaps

    return InMemorySpendLedger(
        SpendCaps(per_user_daily_micro_inr=10**9, global_daily_micro_inr=10**9)
    )


@app.function(
    image=cpu_image,
    volumes={"/work": vol, "/vol": spike_vol},
    cpu=8,
    memory=16384,
    timeout=7200,
    secrets=VISION_SECRETS,
)
def twin_smoke_cpu(scene: str, keyframes: int) -> dict[str, Any]:
    """A whole twin from one ARKitScenes room turned into an AR world (y up), end to end."""
    import asyncio
    import json

    from sajao_workers.steps import LocalArtifactStore, StepRunner

    store = LocalArtifactStore(Path("/work/artifacts"))
    manifest = _arkit_manifest(store, scene, keyframes, y_up=True)
    runner = StepRunner(store, max_attempts=1)

    async def run() -> dict[str, Any]:
        built = await _build_twin(
            store, runner, _ledger(), _arkit_capture(scene, manifest), manifest
        )
        objects, splat, phone, twin = (built[k] for k in ("objects", "splat", "phone", "twin"))
        doc = json.loads(store.read_blob(twin.outputs["twin"]))
        for surface in doc["shell"]["surfaces"]:  # textures to look at
            if "texture" in surface:
                data = store.read_blob(surface["texture"].rsplit("/", 1)[-1])
                await asyncio.to_thread(_save, f"/work/previews/{scene}_{surface['id']}.jpg", data)
        openings = json.loads(store.read_blob(objects.outputs["openings"]))
        vol.commit()
        return {
            "scene": scene,
            "opening_masks": {k: sum(o["kind"] == k for o in openings) for k in ("door", "window")},
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


@app.function(
    image=cpu_image,
    volumes={"/work": vol, "/vol": spike_vol},
    cpu=8,
    memory=16384,
    timeout=7200,
    secrets=VISION_SECRETS,
)
def edit_smoke_cpu(scene: str, keyframes: int) -> dict[str, Any]:
    """Edits on one ARKitScenes room's twin: move and turn the largest sofa, remove a
    chair, replace a table; then phone splats of the edited room."""
    import asyncio
    import json

    from sajao_gateway import ModelGateway
    from sajao_workers.models import removal_chain
    from sajao_workers.steps import LocalArtifactStore, StepRunner
    from sajao_workers.twin.edit_step import edit_step, with_phone_splats
    from sajao_workers.twin.phone_step import phone_splat_step

    store = LocalArtifactStore(Path("/work/artifacts"))
    manifest = _arkit_manifest(store, scene, keyframes, y_up=True)
    runner = StepRunner(store, max_attempts=1)
    ledger = _ledger()

    async def run() -> dict[str, Any]:
        built = await _build_twin(store, runner, ledger, _arkit_capture(scene, manifest), manifest)
        twin = json.loads(store.read_blob(built["twin"].outputs["twin"]))

        def largest(category: str) -> dict[str, Any] | None:
            found = [o for o in twin["objects"] if o["category"] == category]
            volume = lambda o: o["box"]["width"]["value_m"] * o["box"]["depth"]["value_m"]  # noqa: E731
            return max(found, key=volume) if found else None

        sofa, chair, table = largest("sofa"), largest("chair"), largest("table")
        edits: list[dict[str, Any]] = []
        if sofa:
            c = sofa["box"]["center"]
            to = {**c, "x_m": round(c["x_m"] + 0.8, 3)}
            edits.append(
                {"id": "e1", "op": "move", "by": "user", "object_id": sofa["id"], "to": to}
            )
            yaw = (sofa["box"]["yaw_deg"] + 90) % 360
            edits.append(
                {"id": "e2", "op": "rotate", "by": "user", "object_id": sofa["id"], "yaw_deg": yaw}
            )
        if chair:
            edits.append({"id": "e3", "op": "remove", "by": "user", "object_id": chair["id"]})
        if table:
            dim = lambda v: {"value_m": v, "source": "measured", "error_band_m": 0.01}  # noqa: E731
            size = {"width": dim(1.2), "depth": dim(0.6), "height": dim(0.45)}
            edits.append(
                {"id": "e4", "op": "replace", "by": "user", "object_id": table["id"],
                 "product_id": "smoke-coffee-table", "product_size": size}
            )  # fmt: skip
        reference = {"twin_id": twin["id"], "twin_version": twin["version"], "edits": edits}
        splat = built["splat"]
        edited = await runner.run(
            edit_step(
                ModelGateway(removal_chain(volume_invoke("twin_remove", run_splat)), ledger=ledger)
            ),
            {
                "twin": built["twin"].outputs["twin"],
                "frames": built["frames"],
                "objects": built["objects"].outputs["objects"],
                **{k: splat.outputs[k] for k in ("splat", "labels", "cameras")},
            },
            {"reference": reference, "preview": True},
        )
        phone = await runner.run(
            phone_splat_step(_compress), {"splat": edited.outputs["splat"]}, {}
        )
        variants = [
            {"budget": int(tag.rstrip("k")) * 1000, "sog": phone.outputs[f"sog_{tag}"], **v}
            for tag, v in phone.meta["variants"].items()
        ]
        view = with_phone_splats(json.loads(store.read_blob(edited.outputs["view"])), variants)
        preview = None
        if "preview" in edited.outputs:
            preview = f"/work/previews/{scene}_edits.jpg"
            await asyncio.to_thread(_save, preview, store.read_blob(edited.outputs["preview"]))
        vol.commit()
        return {
            "scene": scene,
            "edits": edits,
            "edit": dict(edited.meta),
            "objects_by_state": {
                state: [o["id"] for o in view["objects"] if o["state"] == state]
                for state in ("move", "remove", "replace")
            },
            "phone_mb": {k: round(v["bytes"] / 1e6, 2) for k, v in phone.meta["variants"].items()},
            "preview": preview,
            "charged_micro_inr": edited.cost_micro_inr + phone.cost_micro_inr,
        }

    return asyncio.run(run())


def _capture_file(root: Path, key: str) -> bytes:
    """A file of an uploaded capture folder, by its storage key (or the key's file name)."""
    for path in (root / key, root / Path(key).name):
        if path.is_file():
            return path.read_bytes()
    raise FileNotFoundError(f"{key} is not in the capture folder")


@app.function(
    image=cpu_image,
    volumes={"/work": vol, "/vol": spike_vol},
    cpu=8,
    memory=16384,
    timeout=7200,
    secrets=VISION_SECRETS,
)
def golden_room_cpu(folder: str, sheet: dict[str, Any]) -> dict[str, Any]:
    """An uploaded capture to its twin, and the twin's accuracy against the tape sheet."""
    import asyncio
    import json

    from sajao_gateway import ModelGateway
    from sajao_schemas.generated.v1 import Capture
    from sajao_workers.ar_measurements import measure
    from sajao_workers.ar_openings import openings_from_keyframes
    from sajao_workers.golden import accuracy_report, markdown, read_sheet
    from sajao_workers.golden_ar import ar_markdown, ar_report
    from sajao_workers.models import depth_chain
    from sajao_workers.steps import LocalArtifactStore, StepRunner
    from sajao_workers.twin.capture_frames import frames_manifest
    from sajao_workers.twin.depth_step import depth_step
    from sajao_workers.twin.objects import decode_mask
    from sajao_workers.twin.shell import frame_of

    vol.reload()
    root = Path("/work/golden") / folder
    capture = json.loads((root / "capture.json").read_text())
    Capture.model_validate(capture)
    package = capture["package"]
    store = LocalArtifactStore(Path("/work/artifacts"))
    runner = StepRunner(store, max_attempts=1)
    ledger = _ledger()
    images = {
        k["id"]: store.put_blob(_capture_file(root, k["image"])) for k in package["keyframes"]
    }
    depth = _capture_file(root, package["depth"]) if package.get("depth") else None
    manifest = frames_manifest(package, images, depth, store)
    # The phone's own AR measurements against the same tape: no GPU, no twin.
    planes = json.loads(_capture_file(root, package["planes"])) if package.get("planes") else {}
    ar_measurements = measure(planes)

    async def run() -> dict[str, Any]:
        nonlocal manifest
        depth_meta: dict[str, Any] = {"model": "lidar"}
        if manifest["depth_source"] != "lidar":  # phones without LiDAR: depth from images
            estimated = await runner.run(
                depth_step(ModelGateway(depth_chain(volume_invoke("twin_depth")), ledger=ledger)),
                {"frames": store.put_blob(json.dumps(manifest).encode())},
                {},
            )
            manifest = json.loads(store.read_blob(estimated.outputs["frames"]))
            depth_meta = dict(estimated.meta)
        built = await _build_twin(store, runner, ledger, capture, manifest)
        twin = json.loads(store.read_blob(built["twin"].outputs["twin"]))
        truth, to_space = None, None
        if (root / "ground_truth.json").is_file():  # an annotated dataset room
            from sajao_workers.twin.edits import space_transform

            truth = json.loads((root / "ground_truth.json").read_text())
            to_space = space_transform(twin["keyframes"], manifest["frames"])
        # Doors and windows for the AR measurements: the same masks the twin
        # uses, cast from each keyframe's pose onto the walls the phone measured.
        frames = {f["keyframe_id"]: f for f in manifest["frames"]}
        masks = [
            (o["kind"], decode_mask(store.read_blob(o["mask"])), frame_of(frames[o["keyframe_id"]]))
            for o in json.loads(store.read_blob(built["objects"].outputs["openings"]))
            if o["keyframe_id"] in frames
        ]
        ar_measurements["keyframe_openings"] = openings_from_keyframes(ar_measurements, masks)
        ar = ar_report(ar_measurements, read_sheet(sheet))
        report = accuracy_report(twin, read_sheet(sheet), truth=truth, to_space=to_space)
        charged = sum(built[k].cost_micro_inr for k in ("inventory", "objects", "splat", "phone"))
        return {
            "twin": twin,
            "report": report,
            "markdown": markdown(report),
            "ar": {"measurements": ar_measurements, "report": ar, "markdown": ar_markdown(ar)},
            "run": {
                "depth": depth_meta,
                "objects": dict(built["objects"].meta),
                "splat": dict(built["splat"].meta),
                "twin": dict(built["twin"].meta),
                "charged_micro_inr": charged,
            },
        }

    return asyncio.run(run())


def _quaternion_xyzw(r: Any) -> list[float]:
    """Unit quaternion (x, y, z, w) of a rotation matrix, the capture package's order."""
    import numpy as np

    def part(a: float, b: float, c: float, sign: float) -> float:
        return float(np.copysign(np.sqrt(max(0.0, 1 + a - b - c)) / 2, sign))

    w = float(np.sqrt(max(0.0, 1 + np.trace(r))) / 2)
    return [
        part(r[0, 0], r[1, 1], r[2, 2], r[2, 1] - r[1, 2]),
        part(r[1, 1], r[0, 0], r[2, 2], r[0, 2] - r[2, 0]),
        part(r[2, 2], r[0, 0], r[1, 1], r[1, 0] - r[0, 1]),
        w,
    ]


@app.function(image=cpu_image, volumes={"/work": vol, "/vol": spike_vol}, timeout=1800)
def golden_fixture_cpu(scene: str, keyframes: int) -> str:
    """An ARKitScenes room written as an uploaded capture folder (capture.json, keyframe
    JPEGs, SJDEPTH1 depth), to test the golden-room command before real rooms exist."""
    import json
    import struct
    import uuid

    import numpy as np
    from PIL import Image

    from sajao_schemas.generated.v1 import Capture

    cams = json.loads(Path(f"/vol/scenes/{scene}/cameras.json").read_text())
    turn = _y_up(cams["up"])  # into an AR world, y up, as a phone delivers it
    picks = np.linspace(0, len(cams["frames"]) - 1, keyframes).round().astype(int)
    root = Path(f"/work/golden-fixtures/{scene}")
    (root / "keyframes").mkdir(parents=True, exist_ok=True)
    depth_parts = [b"SJDEPTH1", struct.pack("<I", len(picks))]
    frames, media = [], []
    capture_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"golden-fixture/{scene}"))
    for n, i in enumerate(picks, start=1):
        f = cams["frames"][int(i)]
        base = Path(f"/vol/scenes/{scene}")
        key = f"keyframes/k{n}.jpg"
        (root / key).write_bytes((base / f["file"]).read_bytes())
        c2w = np.asarray(f["c2w"], dtype=np.float64)
        rotation = turn @ c2w[:3, :3] @ np.diag([1.0, -1.0, -1.0])  # OpenCV to AR camera axes
        position = turn @ c2w[:3, 3]
        q = _quaternion_xyzw(rotation)
        k = f["K"]
        frames.append(
            {
                "id": f"k{n}",
                "image": key,
                "captured_at_ms": 250 * n,
                "sharpness": 1.0,
                "pose": {
                    "position": {"x_m": position[0], "y_m": position[1], "z_m": position[2]},
                    "rotation": q,
                },
                "intrinsics": {"fx": k[0][0], "fy": k[1][1], "cx": k[0][2], "cy": k[1][2],
                               "width_px": f["w"], "height_px": f["h"]},
            }
        )  # fmt: skip
        media.append(
            {"id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{capture_id}/{n}")), "kind": "photo",
             "origin": "camera", "storage_key": key, "width_px": f["w"], "height_px": f["h"],
             "has_ar_pose": True}
        )  # fmt: skip
        depth = np.asarray(Image.open(base / f["depth"]), dtype=np.uint16)
        ident = f"k{n}".encode()
        depth_parts += [
            struct.pack("<H", len(ident)),
            ident,
            struct.pack("<II", depth.shape[1], depth.shape[0]),
            depth.astype("<u2").tobytes(),
            np.where(depth > 0, 255, 0).astype(np.uint8).tobytes(),
        ]
    (root / "depth.sjdepth").write_bytes(b"".join(depth_parts))
    (root / "sensor.jsonl").write_text("")
    capture = {
        "schema_version": "1.0",
        "id": capture_id,
        "user_id": str(uuid.uuid5(uuid.NAMESPACE_URL, "golden-fixture/user")),
        "created_at": "2026-11-16T00:00:00Z",
        "media": media[:40],
        "device": {"platform": "ios", "tier": "standard", "has_ar": True},
        # ARKitScenes has no compass reading: a declared test heading, not a measurement.
        "compass": {"mean_heading_deg": 0.0, "sample_count": 1},
        "package": {
            "ar": {"tracking": "arkit", "lidar": True, "depth": True},
            "keyframes": frames,
            "depth": "depth.sjdepth",
            "detections": [],
            "sensor_log": "sensor.jsonl",
        },
    }
    Capture.model_validate(capture)
    (root / "capture.json").write_text(json.dumps(capture, indent=1))
    # Annotated boxes the capture saw, in its AR world: for box size errors (golden.py).
    from twin_gpu.objects import gt_boxes, gt_seen

    up_axis = int(np.argmax(np.abs(np.asarray(cams["up"], dtype=np.float64))))
    gts = gt_boxes(scene, up_axis)
    truth = [
        {
            "label": g.label,
            "center": [round(float(v), 4) for v in turn @ np.asarray(g.box.center)],
            "size_m": [round(g.box.length, 3), round(g.box.width, 3), round(g.box.height, 3)],
        }
        for g, seen in zip(gts, gt_seen(scene, gts), strict=True)
        if seen
    ]
    (root / "ground_truth.json").write_text(json.dumps(truth, indent=1))
    vol.commit()
    return str(root)


@app.local_entrypoint()
def golden_fixture(scene: str = "arkit_living_47331265", keyframes: int = 120) -> None:
    print(golden_fixture_cpu.remote(scene, keyframes))


@app.local_entrypoint()
def golden_room(capture: str, tape: str, out: str = "") -> None:
    """One golden room: `--capture` is the uploaded capture folder (capture.json plus the
    files its storage keys name), `--tape` the measurement sheet (eval/golden). Writes the
    twin, the report as JSON and Markdown, and run details to `--out`."""
    import json
    import re

    from sajao_workers.golden import read_sheet

    sheet = json.loads(Path(tape).read_text())
    room = read_sheet(sheet).room or Path(capture).name  # a bad sheet stops here, before any GPU
    slug = re.sub(r"[^a-z0-9]+", "-", room.lower()).strip("-") or "room"
    if not (Path(capture) / "capture.json").is_file():
        raise SystemExit(f"{capture} has no capture.json: pass the capture folder itself")
    with vol.batch_upload(force=True) as batch:
        batch.put_directory(capture, f"golden/{slug}")
    result = golden_room_cpu.remote(slug, sheet)
    target = Path(out or f"golden-runs/{slug}")
    target.mkdir(parents=True, exist_ok=True)
    (target / "twin.json").write_text(json.dumps(result["twin"], indent=1) + "\n")
    (target / "report.json").write_text(json.dumps(result["report"], indent=1) + "\n")
    (target / "report.md").write_text(result["markdown"])
    (target / "run.json").write_text(json.dumps(result["run"], indent=1) + "\n")
    ar = result["ar"]
    (target / "ar-measurements.json").write_text(json.dumps(ar["measurements"], indent=1) + "\n")
    (target / "ar-report.json").write_text(json.dumps(ar["report"], indent=1) + "\n")
    (target / "ar-report.md").write_text(ar["markdown"])
    print(ar["markdown"])
    print(result["markdown"])
    print(f"Written to {target}")


@app.local_entrypoint()
def edit_smoke(scene: str = "arkit_living_47331265", keyframes: int = 120) -> None:
    import json

    print(json.dumps(edit_smoke_cpu.remote(scene, keyframes), indent=1))


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
            "inputs": {
                "splat": splat.outputs["splat"],
                "removed": removed.outputs["splat"],
                "cameras": splat.outputs["cameras"],
                "frames": frames,
                "objects": objects.outputs["objects"],
            },
        }

    return asyncio.run(run())


@app.local_entrypoint()
def removal_smoke(
    scene: str = "arkit_living_47331265", keyframes: int = 120, category: str = "sofa"
) -> None:
    import json

    print(json.dumps(removal_smoke_cpu.remote(scene, keyframes, category), indent=1))


@app.function(
    image=cpu_image, volumes={"/work": vol, "/vol": spike_vol}, cpu=8, memory=16384, timeout=3600
)
def shell_smoke_cpu(scene: str, keyframes: int, detectors: str) -> dict[str, Any]:
    """The shell alone (walls, doors, windows, textures) from the objects step's masks, with
    a chosen detector chain: no splat, so it is quick to iterate on."""
    import asyncio
    import json

    from sajao_gateway import ModelGateway
    from sajao_workers.models import detect_chain, detector_order, segment_chain
    from sajao_workers.steps import LocalArtifactStore, StepRunner
    from sajao_workers.twin.assemble_step import _shell_from_frames, shell_points
    from sajao_workers.twin.objects_step import objects_step
    from sajao_workers.twin.space import fit_space

    store = LocalArtifactStore(Path("/work/artifacts"))
    manifest = _arkit_manifest(store, scene, keyframes, y_up=True)
    chosen = {"SAJAO_DETECTORS": detectors} if detectors else {}
    ledger = _ledger()
    objects = asyncio.run(
        StepRunner(store, max_attempts=1).run(
            objects_step(
                ModelGateway(
                    detect_chain(volume_invoke("twin_detect"), order=detector_order(chosen)),
                    ledger=ledger,
                ),
                ModelGateway(segment_chain(volume_invoke("twin_segment")), ledger=ledger),
            ),
            {"frames": store.put_blob(json.dumps(manifest).encode())},
            chosen,
        )
    )
    found = json.loads(store.read_blob(objects.outputs["objects"]))
    openings = json.loads(store.read_blob(objects.outputs["openings"]))
    space = fit_space(shell_points(store, manifest), depth_source=manifest["depth_source"])
    coverage = _shell_from_frames(store, manifest, found, openings, space, textures=True)
    for surface in space.shell["surfaces"]:
        if "texture" in surface:
            data = store.read_blob(surface["texture"].rsplit("/", 1)[-1])
            _save(f"/work/previews/{scene}_{detectors or 'default'}_{surface['id']}.jpg", data)
    vol.commit()
    return {
        "scene": scene,
        "detector": objects.meta["detector"],
        "opening_masks": {k: sum(o["kind"] == k for o in openings) for k in ("door", "window")},
        "walls": [(w["id"], w["length"]["value_m"]) for w in space.shell["walls"]],
        "openings": space.shell["openings"],
        "texture_coverage": coverage,
        "charged_micro_inr": objects.cost_micro_inr,
    }


@app.local_entrypoint()
def shell_smoke(
    scene: str = "arkit_living_47331265", keyframes: int = 120, detectors: str = "owlv2"
) -> None:
    import json

    print(json.dumps(shell_smoke_cpu.remote(scene, keyframes, detectors), indent=1))


@app.local_entrypoint()
def twin_smoke(scene: str = "arkit_living_47331265", keyframes: int = 120) -> None:
    import json

    print(json.dumps(twin_smoke_cpu.remote(scene, keyframes), indent=1))


@app.function(
    image=cpu_image,
    volumes={"/work": vol, "/vol": spike_vol},
    cpu=8,
    memory=16384,
    timeout=3600,
    secrets=VISION_SECRETS,
)
def inventory_eval_cpu(
    scene: str, keyframes: int, hand: dict[str, Any], detectors: str, listing_only: bool = False
) -> dict[str, Any]:
    """One ARKitScenes room: the inventory, the objects placed from it, and recall per type
    against the hand inventory (eval/twin-inventory)."""
    import asyncio
    import json

    from sajao_workers.inventory_recall import (
        big_item_placement,
        listing_recall_by_geometry,
        recall_report,
    )
    from sajao_workers.steps import LocalArtifactStore, StepRunner

    store = LocalArtifactStore(Path("/work/artifacts"))
    manifest = _arkit_manifest(store, scene, keyframes)
    runner = StepRunner(store, max_attempts=1)
    frames = store.put_blob(json.dumps(manifest).encode())
    if listing_only:  # the vision models' list alone: no GPU
        from twin_gpu.objects import gt_boxes, gt_seen

        from sajao_workers.twin.inventory_step import inventory_step

        step = inventory_step(*_inventory_gateways(_ledger()))
        listing = asyncio.run(runner.run(step, {"frames": frames}, {}))
        vol.commit()
        listed = json.loads(store.read_blob(listing.outputs["inventory"]))
        gts = gt_boxes(scene, manifest["up_axis"])
        seen = [{"label": g.label} for g, ok in zip(gts, gt_seen(scene, gts), strict=True) if ok]
        return {
            "scene": scene,
            "detectors": "listing",
            "inventory": listed,
            "recall": recall_report(hand, listed, [], []),
            "listing_by_geometry": listing_recall_by_geometry(seen, listed["items"]),
            "inventory_meta": dict(listing.meta),
            "charged_micro_inr": listing.cost_micro_inr,
        }
    inventory, objects = asyncio.run(_objects(runner, _ledger(), frames, detectors))
    vol.commit()

    def read(result: Any, name: str) -> Any:
        return json.loads(store.read_blob(result.outputs[name]))

    listed = read(inventory, "inventory")
    placed, built_ins = read(objects, "objects"), read(objects, "built_ins")
    from twin_gpu.objects import gt_boxes, gt_seen

    gts = gt_boxes(scene, manifest["up_axis"])
    truth = [
        {"label": g.label, "center": list(g.box.center), "yaw": g.box.yaw,
         "size_m": [g.box.length, g.box.width, g.box.height]}
        for g, seen in zip(gts, gt_seen(scene, gts), strict=True)
        if seen
    ]  # fmt: skip
    return {
        "scene": scene,
        "detectors": detectors or "default",
        "recall": recall_report(hand, listed, placed, built_ins),
        "inventory": listed,
        "placement": read(objects, "inventory"),
        "objects": [
            {
                "category": o["category"],
                "type": o["object_type"],
                "frames": o["frames"],
                "size_m": [o["box"][k]["value_m"] for k in ("length", "width", "height")],
            }
            for o in placed
        ]
        + [{"category": b["category"], "type": "built_in"} for b in built_ins],
        "boxes": [
            {k: o[k] for k in ("category", "confidence", "frames", "box", "object_type", "up_axis")}
            for o in placed
        ]
        + [{k: b[k] for k in ("category", "confidence", "frames", "box")} for b in built_ins],
        "ground_truth": truth,
        "listing_by_geometry": listing_recall_by_geometry(truth, listed["items"]),
        "big_item_placement": big_item_placement([*placed, *built_ins], truth),
        "inventory_meta": dict(inventory.meta),
        "objects_meta": dict(objects.meta),
        "charged_micro_inr": inventory.cost_micro_inr + objects.cost_micro_inr,
    }


@app.local_entrypoint()
def inventory_eval(
    detectors: str = "", keyframes: int = 120, out: str = "", rooms: str = "", listing: bool = False
) -> None:
    """Recall per type on the ARKit rooms with hand inventories; one result file per room."""
    import json

    hand_dir = Path(__file__).parents[3] / "eval" / "twin-inventory" / "hand"
    wanted = set(rooms.split(",")) if rooms else None
    hands = {
        p.stem: json.loads(p.read_text())
        for p in sorted(hand_dir.glob("*.json"))
        if wanted is None or p.stem in wanted
    }
    target = Path(out or "inventory-runs")
    target.mkdir(parents=True, exist_ok=True)
    args = [(scene, keyframes, hand, detectors, listing) for scene, hand in hands.items()]
    for result in inventory_eval_cpu.starmap(args, return_exceptions=True):
        if isinstance(result, BaseException):
            print(f"failed: {type(result).__name__}: {result}")
            continue
        name = f"{result['scene']}.{result['detectors'].replace(',', '-')}.json"
        (target / name).write_text(json.dumps(result, indent=1) + "\n")
        geometry = result["listing_by_geometry"]
        print(result["scene"], json.dumps(result["recall"]["listed"]["all"]),
              f"geometry {geometry['covered']} of {geometry['annotated']}")  # fmt: skip


@app.function(
    image=cpu_image, volumes={"/work": vol, "/vol": spike_vol}, cpu=8, memory=16384, timeout=7200
)
def review_pack_cpu(scene: str, keyframes: int, category: str) -> dict[str, Any]:
    """A visual review of one room's twin: renders from the splat (see review_gpu).

    The objects, splat and removal steps are the removal smoke's, so stored results are
    reused; only the renders are new GPU work."""
    import io
    import json

    import imageio.v2 as imageio
    import numpy as np
    from PIL import Image

    from sajao_workers.models import GSPLAT
    from sajao_workers.steps import LocalArtifactStore

    smoke = removal_smoke_cpu.local(scene, keyframes, category)
    if "error" in smoke:
        return smoke
    store = LocalArtifactStore(Path("/work/artifacts"))
    vol.reload()
    payload = {**smoke["inputs"], "removed_index": int(smoke["object"][1:])}
    reply = run_splat.remote(GSPLAT, "twin_review", payload)
    if "error" in reply:
        return {"scene": scene, "error": reply["error"]}
    vol.reload()
    out = reply["output"]
    video = io.BytesIO()
    with imageio.get_writer(
        video, format="mp4", fps=out["fps"], codec="libx264", quality=8, macro_block_size=8
    ) as writer:
        for digest in out["video_frames"]:
            writer.append_data(np.asarray(Image.open(io.BytesIO(store.read_blob(digest)))))
    files: dict[str, bytes] = {"flythrough.mp4": video.getvalue()}
    for still in [*out["stills"], *out["extremes"]]:
        files[f"{still['name']}.jpg"] = store.read_blob(still["image"])
    files["boxes.jpg"] = store.read_blob(out["boxes"]["image"])
    files["control_photo_vs_render.jpg"] = store.read_blob(out["control"])
    for view, pair in out["removal"].items():
        before = Image.open(io.BytesIO(store.read_blob(pair["before"])))
        after = Image.open(io.BytesIO(store.read_blob(pair["after"])))
        side = Image.new("RGB", (before.width * 2 + 8, before.height), "white")
        side.paste(before, (0, 0))
        side.paste(after, (before.width + 8, 0))
        buf = io.BytesIO()
        side.save(buf, format="JPEG", quality=92)
        files[f"removal_{view}_before_after.jpg"] = buf.getvalue()
    summary = {
        "scene": scene,
        "removed": {"object": smoke["object"], "category": category, **smoke["removal"]},
        "stills": [
            {k: v for k, v in s.items() if k not in ("image", "c2w")}
            for s in [*out["stills"], *out["extremes"]]
        ],
        "candidate_scores": out["candidate_scores"],
        "video_nearest_training_camera_m": out["video_nearest_m"],
        "boxes": {"from": out["boxes"]["from"], "labels": out["boxes"]["labels"]},
        "removal_views": {
            v: {k: x for k, x in p.items() if k not in ("before", "after")}
            for v, p in out["removal"].items()
        },
        "room": out["room"],
        "gpu_seconds": reply["gpu_seconds"],
    }
    files["summary.json"] = (json.dumps(summary, indent=1) + "\n").encode()
    return {"files": files, "summary": summary}


@app.local_entrypoint()
def review_pack(
    scene: str = "arkit_living_47331265",
    keyframes: int = 120,
    category: str = "sofa",
    out: str = "review-pack",
) -> None:
    result = review_pack_cpu.remote(scene, keyframes, category)
    if "files" not in result:
        print(result)
        return
    target = Path(out)
    target.mkdir(parents=True, exist_ok=True)
    for name, data in result["files"].items():
        (target / name).write_bytes(data)
    print(result["files"]["summary.json"].decode())


@app.function(
    image=cpu_image,
    volumes={"/work": vol, "/vol": spike_vol},
    cpu=8,
    memory=16384,
    timeout=7200,
    secrets=VISION_SECRETS,
)
def understanding_smoke_cpu(scene: str, keyframes: int) -> dict[str, Any]:
    """One ARKitScenes room without the splat: inventory, objects, the twin, then room
    understanding for design. Draws the hero masks and the floor plan to look at."""
    import asyncio
    import io
    import json

    import numpy as np
    from PIL import Image, ImageDraw

    from sajao_gateway import ModelGateway
    from sajao_workers.models import segment_chain
    from sajao_workers.steps import LocalArtifactStore, StepRunner
    from sajao_workers.twin.assemble_step import assemble_step
    from sajao_workers.twin.understanding_step import understanding_step

    store = LocalArtifactStore(Path("/work/artifacts"))
    manifest = _arkit_manifest(store, scene, keyframes, y_up=True)
    runner = StepRunner(store, max_attempts=1)
    ledger = _ledger()

    async def run() -> dict[str, Any]:
        frames = store.put_blob(json.dumps(manifest).encode())
        inventory, objects = await _objects(runner, ledger, frames)
        twin = await runner.run(
            assemble_step(),
            {
                "capture": store.put_blob(json.dumps(_arkit_capture(scene, manifest)).encode()),
                "frames": frames,
                "objects": objects.outputs["objects"],
                "openings": objects.outputs["openings"],
                "built_ins": objects.outputs["built_ins"],
                "inventory": objects.outputs["inventory"],
                "phone": store.put_blob(json.dumps({"variants": {}}).encode()),
            },
            {
                "twin_id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"twin/{scene}/nosplat")),
                "version": 1,
                "created_at": "2026-11-17T00:00:00Z",
            },
        )
        understood = await runner.run(
            understanding_step(
                ModelGateway(segment_chain(volume_invoke("twin_segment")), ledger=ledger)
            ),
            {
                "twin": twin.outputs["twin"],
                "objects": objects.outputs["objects"],
                "frames": frames,
            },
            {},
        )
        vol.commit()
        return {
            "inventory": inventory,
            "objects": objects,
            "twin": twin,
            "understood": understood,
        }

    import uuid

    built = asyncio.run(run())
    doc = json.loads(store.read_blob(built["understood"].outputs["twin"]))
    by_kf = {f["keyframe_id"]: f for f in manifest["frames"]}

    def blob(key: str) -> bytes:
        return store.read_blob(key.rsplit("/", 1)[-1])

    files: dict[str, bytes] = {}
    colours = {"detected": (40, 120, 255), "prompted": (255, 140, 0)}
    for hero in doc["viewing"]["hero_views"]:
        frame = by_kf[hero["keyframe_id"]]
        photo = np.asarray(Image.open(io.BytesIO(store.read_blob(frame["image"]))).convert("RGB"))
        canvas = photo.astype(np.float32)
        labels = []
        for obj in doc["objects"]:
            for m in obj.get("hero_masks", []):
                if m["hero_view_id"] != hero["id"]:
                    continue
                mask = np.asarray(Image.open(io.BytesIO(blob(m["mask"]))).convert("L")) > 127
                if mask.shape != photo.shape[:2]:
                    mask = (
                        np.asarray(
                            Image.fromarray(mask.astype(np.uint8) * 255).resize(photo.shape[1::-1])
                        )
                        > 127
                    )
                canvas[mask] = 0.45 * canvas[mask] + 0.55 * np.array(colours[m["source"]])
                ys, xs = np.nonzero(mask)
                if len(xs):
                    labels.append(
                        (int(xs.mean()), int(ys.mean()), obj["category"], obj["redesign"]["state"])
                    )
        image = Image.fromarray(canvas.clip(0, 255).astype(np.uint8))
        draw = ImageDraw.Draw(image)
        for x, y, name, state in labels:
            draw.text((x, y), f"{name} ({state})", fill=(255, 255, 255))
        buf = io.BytesIO()
        image.save(buf, format="JPEG", quality=88)
        files[f"hero_{hero['id']}_masks.jpg"] = buf.getvalue()

    floor = doc["shell"]["floor_polygon"]
    xs = [p["x_m"] for p in floor]
    ys = [p["y_m"] for p in floor]
    scale = 120.0
    size = (int((max(xs) - min(xs)) * scale) + 40, int((max(ys) - min(ys)) * scale) + 40)

    def to_px(p: dict[str, float]) -> tuple[float, float]:
        return (20 + (p["x_m"] - min(xs)) * scale, size[1] - 20 - (p["y_m"] - min(ys)) * scale)

    plan = Image.new("RGB", size, (250, 247, 240))
    draw = ImageDraw.Draw(plan)
    draw.polygon([to_px(p) for p in floor], outline=(40, 40, 40), fill=(235, 245, 235))
    for thing in [*doc["objects"], *doc["shell"].get("built_ins", [])]:
        fp = thing.get("footprint")
        if not fp or not fp["on_floor"]:
            continue
        kept = thing.get("redesign", {"state": "keep"})["state"] == "keep"
        draw.polygon(
            [to_px(p) for p in fp["polygon"]],
            outline=(173, 79, 39) if not kept else (60, 60, 60),
            fill=(150, 150, 150) if kept else None,
        )
        c = thing["box"]["center"]
        draw.text(to_px({"x_m": c["x_m"], "y_m": c["y_m"]}), thing["category"], fill=(0, 0, 0))
    ff = doc["free_floor"]
    draw.text(
        (24, 4),
        f"free floor {ff['area_m2']:.1f} of {ff['floor_area_m2']:.1f} m2"
        f" (+/- {ff['error_band_m2']:.1f})",
        fill=(0, 0, 0),
    )
    buf = io.BytesIO()
    plan.save(buf, format="PNG")
    files["floor_plan.png"] = buf.getvalue()
    files["twin.json"] = json.dumps(doc, indent=1).encode()
    steps = built
    summary = {
        "scene": scene,
        "objects": len(doc["objects"]),
        "built_ins": len(doc["shell"].get("built_ins", [])),
        "hero_views": len(doc["viewing"]["hero_views"]),
        "hero_masks": dict(steps["understood"].meta["hero_masks"]),
        "free_floor": doc["free_floor"],
        "redesign": {
            s: sum(o["redesign"]["state"] == s for o in doc["objects"]) for s in ("keep", "replace")
        },
        "on_floor": sum(o["footprint"]["on_floor"] for o in doc["objects"]),
        "charged_micro_inr": sum(steps[k].cost_micro_inr for k in steps),
    }
    files["summary.json"] = (json.dumps(summary, indent=1) + "\n").encode()
    return {"files": files, "summary": summary}


@app.local_entrypoint()
def understanding_smoke(
    scene: str = "arkit_living_47331265", keyframes: int = 120, out: str = "understanding"
) -> None:
    import json

    result = understanding_smoke_cpu.remote(scene, keyframes)
    target = Path(out)
    target.mkdir(parents=True, exist_ok=True)
    for name, data in result["files"].items():
        (target / name).write_bytes(data)
    print(json.dumps(result["summary"], indent=1))
