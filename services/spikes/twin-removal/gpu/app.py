"""Modal app for the object removal comparison: fill B with LaMa versus Qwen-Image.

Reads the SJ-116 spike's splats and masks from the `sajao-twin-risk` volume and
writes results to out/<scene>/removal/<kind>/. Stages run one after another and
each is capped, so the run never holds more than three GPUs.

    uv run --with 'modal[api-proxy-support]==1.6.4' modal run services/spikes/twin-removal/gpu/app.py
    python services/spikes/twin-removal/gpu/collect.py

Internal evaluation on public datasets only.
"""

from __future__ import annotations

from pathlib import Path

import modal

HERE = Path(__file__).resolve().parent
SPIKE = HERE.parent.parent / "twin-risk"
SRC = SPIKE / "src" / "twin_risk"

# Copied unchanged from the SJ-116 spike so Modal reuses its cached image layers.
MAPANYTHING_REF = "3d10cf7a3016fc0f9bb13a071ee66c47b10be0d9"

gpu_image = (
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
        "printf 'torch==2.4.1\\ntorchvision==0.19.1\\ntorchaudio==2.4.1\\nnumpy==2.1.3\\n' > /constraints.txt"
    )
    .env({"PIP_CONSTRAINT": "/constraints.txt"})
    .pip_install("numpy==2.1.3", "ninja==1.11.1.3", "jaxtyping==0.2.36", "rich==13.9.4")
    # No prebuilt gsplat wheel exists for Python 3.11 with torch 2.4, so build it
    # here for T4 (7.5), A10G (8.6), L4 and L40S (8.9).
    .env({"TORCH_CUDA_ARCH_LIST": "7.5;8.6;8.9", "MAX_JOBS": "8"})
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
eval_image = (
    gpu_image.pip_install("lpips==0.1.4")
    .add_local_dir(SRC, "/root/twin_risk")
    .add_local_dir(SPIKE / "gpu" / "twin_gpu", "/root/twin_gpu")
    .add_local_dir(HERE, "/root", ignore=["app.py"])
)

qwen_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("libgl1", "libglib2.0-0")
    .pip_install(
        "torch==2.8.0",
        "numpy==2.1.3",
        "pillow==11.0.0",
        "opencv-python-headless==4.10.0.84",
        "diffusers==0.43.0",
        "transformers==5.23.0",
        "accelerate==1.15.0",
        "peft==0.21.3",
    )
    .env({"HF_HOME": "/vol/hf", "HF_HUB_DISABLE_XET": "1", "PYTHONUNBUFFERED": "1"})
    .add_local_dir(SPIKE / "gpu" / "twin_gpu", "/root/twin_gpu")
    .add_local_dir(HERE, "/root", ignore=["app.py"])
)

app = modal.App("sajao-twin-removal-eval")
vol = modal.Volume.from_name("sajao-twin-risk")
V = {"/vol": vol}
CASES = [
    ("arkit_living_47331265", "large"),
    ("arkit_living_47331265", "small"),
    ("arkit_living_41159541", "large"),
    ("arkit_living_41159541", "small"),
]


@app.function(image=eval_image, volumes=V, gpu="L40S", timeout=3600, max_containers=1)
def prepare_and_lama(name: str, kind: str) -> dict:
    import time

    import removal

    vol.reload()
    started = time.time()
    prep = removal.prepare(name, kind)
    lama = removal.inpaint_lama(name, kind)
    vol.commit()
    return {"case": [name, kind], "prep": prep, "lama": lama, "gpu_seconds": time.time() - started}


@app.function(image=qwen_image, volumes=V, gpu="H100", timeout=3 * 3600, max_containers=1)
def qwen_inpaint(name: str, kind: str) -> dict:
    import time

    import numpy as np
    import qwen
    from prep_io import load_prep, removal_dir, train_rgb
    from twin_gpu.common import save_json

    vol.reload()
    done = removal_dir(name, kind) / "inpaint_qwen.json"
    if done.exists() and (done.parent / "inpaint_qwen.npz").exists():
        import json

        return {**json.loads(done.read_text()), "gpu_seconds": 0, "reused": True}
    started = time.time()
    qwen.pipeline()
    loaded = time.time()
    prep = load_prep(name, kind)
    frames = [
        qwen.inpaint(train_rgb(name, prep["frames"][j]), prep["holes"][j], seed=int(j))
        for j in prep["inpaint"]
    ]
    inpaint_seconds = time.time() - loaded
    known = [
        qwen.inpaint(train_rgb(name, prep["frames"][j]), m, seed=int(j))
        for j, m in zip(prep["known"], prep["known_holes"], strict=True)
    ]
    d = removal_dir(name, kind)
    np.savez_compressed(
        d / "inpaint_qwen.npz",
        frames=np.stack(frames),
        known=np.stack(known) if known else np.zeros((0,)),
    )
    out = {
        "model": "qwen",
        "frames": len(frames),
        "load_seconds": round(loaded - started, 1),
        "inpaint_seconds": round(inpaint_seconds, 1),
        "seconds_per_frame": round(inpaint_seconds / max(1, len(frames)), 2),
    }
    save_json(d / "inpaint_qwen.json", out)
    vol.commit()
    return {**out, "gpu_seconds": time.time() - started}


@app.function(image=qwen_image, volumes=V, gpu="H100", timeout=3 * 3600, max_containers=1)
def qwen_full_known(name: str, kind: str) -> dict:
    """Ablation: full Qwen-Image (40 steps, guidance 4, negative prompt) on the known-truth holes."""
    import time

    import numpy as np
    import qwen
    from prep_io import load_prep, removal_dir, train_rgb

    vol.reload()
    started = time.time()
    prep = load_prep(name, kind)
    known = [
        qwen.inpaint(train_rgb(name, prep["frames"][j]), m, seed=int(j), full=True)
        for j, m in zip(prep["known"], prep["known_holes"], strict=True)
    ]
    np.savez_compressed(removal_dir(name, kind) / "inpaint_qwen_full.npz", known=np.stack(known))
    vol.commit()
    return {
        "case": [name, kind],
        "holes": len(known),
        "gpu_seconds": round(time.time() - started, 1),
    }


@app.function(image=eval_image, volumes=V, gpu="L40S", timeout=1800, max_containers=1)
def score_known(name: str, kind: str, model: str) -> dict:
    import removal
    from twin_gpu.common import save_json

    vol.reload()
    out = {"case": [name, kind], "model": model, **removal.known_truth_scores(name, kind, model)}
    save_json(removal.removal_dir(name, kind) / f"known_{model}.json", out)
    vol.commit()
    return out


@app.function(image=eval_image, volumes=V, gpu="L40S", timeout=3 * 3600, max_containers=2)
def refill(name: str, kind: str) -> dict:
    import removal

    vol.reload()
    out = removal.refill(name, kind, ["lama", "qwen", "lama_all"])
    vol.commit()
    return out


@app.local_entrypoint()
def main(stage: str = "all") -> None:
    import json

    if stage in ("all", "prepare"):
        for r in prepare_and_lama.starmap(CASES):
            print(json.dumps(r))
    if stage in ("all", "qwen"):
        for r in qwen_inpaint.starmap(CASES):
            print(json.dumps(r))
    if stage == "ablation":
        large = [c for c in CASES if c[1] == "large"]
        for r in qwen_full_known.starmap(large, return_exceptions=True):
            print(json.dumps(r if isinstance(r, dict) else {"failed": repr(r)[:500]}))
        for r in score_known.starmap([(*c, "qwen_full") for c in large], return_exceptions=True):
            print(json.dumps(r if isinstance(r, dict) else {"failed": repr(r)[:500]}))
    if stage in ("all", "refill"):
        for r in refill.starmap(CASES, return_exceptions=True):
            print(json.dumps(r if isinstance(r, dict) else {"failed": repr(r)[:500]}))
