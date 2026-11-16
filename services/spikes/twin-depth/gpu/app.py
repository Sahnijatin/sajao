"""Modal app for the no-LiDAR depth benchmark: commercial models versus MapAnything.

Reads the SJ-116 spike's ARKitScenes rooms and YOLOE masks from the
`sajao-twin-risk` volume. GPU calls run one after another, so the run never holds more
than one GPU at a time; scoring runs on CPU.

    uv run --with 'modal[api-proxy-support]==1.6.4' modal run services/spikes/twin-depth/gpu/app.py

Internal evaluation on public datasets only.
"""

from __future__ import annotations

from pathlib import Path

import modal

HERE = Path(__file__).resolve().parent
SPIKE = HERE.parent.parent / "twin-risk"
SRC = SPIKE / "src" / "twin_risk"
DA3_REF = "3d835ec1a5802d64a8b8b15f817a1ab54809bfe4"
MOGE_REF = "74fbce054ebed49800de42d0ad0e83495065719a"

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
cpu_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install(
        "curl",
        "unzip",
        "pigz",
        "ca-certificates",
        "gnupg",
        "libx11-6",
        "libgl1",
        "libgomp1",
        "libegl1",
    )
    .run_commands(
        "curl -fsSL https://deb.nodesource.com/setup_22.x | bash -",
        "apt-get install -y nodejs",
        "npm install -g @playcanvas/splat-transform@3.11.2",
    )
    .pip_install(
        "numpy==2.1.3",
        "opencv-python-headless==4.10.0.84",
        "open3d==0.19.0",
        "trimesh==4.5.3",
        "pycolmap==3.10.0",
        "pillow==11.0.0",
    )
    .env({"PYTHONUNBUFFERED": "1"})
)


def mounted(image: modal.Image) -> modal.Image:
    return (
        image.add_local_dir(SRC, "/root/twin_risk")
        .add_local_dir(SPIKE / "gpu" / "twin_gpu", "/root/twin_gpu")
        .add_local_dir(HERE, "/root", ignore=["app.py"])
    )


da3_image = (
    modal.Image.from_registry("nvidia/cuda:12.8.1-cudnn-devel-ubuntu22.04", add_python="3.11")
    .apt_install("git", "libgl1", "libglib2.0-0")
    .pip_install("torch==2.8.0", "torchvision==0.23.0", "xformers==0.0.32.post2")
    .pip_install(
        f"depth-anything-3 @ git+https://github.com/ByteDance-Seed/Depth-Anything-3@{DA3_REF}"
    )
    .env({"HF_HOME": "/vol/hf", "PYTHONUNBUFFERED": "1"})
)
moge_image = (
    modal.Image.from_registry("nvidia/cuda:12.8.1-cudnn-devel-ubuntu22.04", add_python="3.11")
    .apt_install("git", "libgl1", "libglib2.0-0", "build-essential")
    .pip_install("torch==2.8.0", "torchvision==0.23.0")
    .pip_install(f"moge @ git+https://github.com/microsoft/MoGe@{MOGE_REF}")
    .env({"HF_HOME": "/vol/hf", "PYTHONUNBUFFERED": "1"})
)

# Same lists as depth_eval.py, kept here so the local entrypoint needs no numpy.
ROOMS = [
    "arkit_living_47331265",
    "arkit_living_41159541",
    "arkit_living_41159566",
    "arkit_bedroom_47430034",
    "arkit_bedroom_47895350",
]
MODELS = ["lidar", "mapanything", "mapanything_apache", "da3_metric", "moge3"]

app = modal.App("sajao-twin-depth-eval")
vol = modal.Volume.from_name("sajao-twin-risk")
V = {"/vol": vol}


@app.function(image=mounted(gpu_image), volumes=V, gpu="L40S", timeout=3600, max_containers=1)
def mapanything(name: str, model: str) -> dict:
    import depth_eval

    vol.reload()
    out = depth_eval.predict_mapanything(name, model)
    vol.commit()
    return out


@app.function(image=mounted(da3_image), volumes=V, gpu="L40S", timeout=3600, max_containers=1)
def da3(name: str) -> dict:
    import depth_eval

    vol.reload()
    out = depth_eval.predict_da3(name)
    vol.commit()
    return out


@app.function(image=mounted(moge_image), volumes=V, gpu="L40S", timeout=3600, max_containers=1)
def moge(name: str) -> dict:
    import depth_eval

    vol.reload()
    out = depth_eval.predict_moge(name)
    vol.commit()
    return out


@app.function(image=mounted(cpu_image), volumes=V, cpu=8, memory=16384, timeout=3600)
def score(name: str, model: str) -> dict:
    import depth_eval

    vol.reload()
    out = depth_eval.score(name, model)
    vol.commit()
    return out


@app.local_entrypoint()
def main(stage: str = "all", rooms: str = "") -> None:
    import json

    names = rooms.split(",") if rooms else ROOMS
    if stage in ("all", "predict"):
        # One GPU call at a time, so this run adds at most one GPU to whatever else is running.
        jobs = [(mapanything, (n, m)) for n in names for m in ("mapanything", "mapanything_apache")]
        jobs += [(da3, (n,)) for n in names] + [(moge, (n,)) for n in names]
        for function, args in jobs:
            try:
                print(json.dumps(function.remote(*args)))
            except Exception as error:  # one failing model must not hide the others' results
                print(json.dumps({"failed": [function.tag, *args], "error": repr(error)[:500]}))
    if stage in ("all", "score"):
        for r in score.starmap([(n, m) for n in names for m in MODELS], return_exceptions=True):
            print(json.dumps(r if isinstance(r, dict) else {"failed": repr(r)[:500]}))
