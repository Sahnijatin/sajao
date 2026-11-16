"""Modal app for the no-AR pose benchmark (AR scan review, Step 2).

Feed-forward poses from images, MoGe-3 depth, scale from each source, against
the AR-pose path on the five SJ-116 ARKitScenes rooms. One GPU at a time;
scoring on CPU. Internal evaluation on public datasets only.

    M="uv run --with modal[api-proxy-support]==1.6.4 modal run services/spikes/twin-noar/gpu/app.py"
    $M --stage poses && $M --stage score && $M --stage splat
"""

from __future__ import annotations

from pathlib import Path

import modal

HERE = Path(__file__).resolve().parent
SPIKES = HERE.parent.parent
SPIKE = SPIKES / "twin-risk"
SRC = SPIKE / "src" / "twin_risk"
WORKERS = SPIKES.parent / "workers"

VGGT_REF = "a288dd0f14786c93483e45524328726ab7b1b4ce"

# The SJ-116 spike's image, unchanged, so Modal reuses its cached layers.
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


# VGGT declares numpy<2 only; its imports (einops, safetensors, huggingface_hub) are
# already in the spike image, so it is installed without its list.
vggt_image = gpu_image.pip_install(
    f"vggt @ git+https://github.com/facebookresearch/vggt@{VGGT_REF}", extra_options="--no-deps"
).run_commands("python -c 'import einops, safetensors; from vggt.models.vggt import VGGT'")


def mounted(image: modal.Image) -> modal.Image:
    return (
        image.add_local_dir(SRC, "/root/twin_risk")
        .add_local_dir(SPIKE / "gpu" / "twin_gpu", "/root/twin_gpu")
        .add_local_file(SPIKES / "twin-depth" / "gpu" / "depth_eval.py", "/root/depth_eval.py")
        .add_local_file(HERE / "noar_eval.py", "/root/noar_eval.py")
        .add_local_dir(WORKERS / "src" / "sajao_workers", "/root/sajao_workers")
        .add_local_file(WORKERS / "gpu" / "splat_gpu.py", "/root/splat_gpu.py")
    )


app = modal.App("sajao-twin-noar-eval")
vol = modal.Volume.from_name("sajao-twin-risk")
V = {"/vol": vol}
ROOMS = [
    "arkit_living_47331265",
    "arkit_living_41159541",
    "arkit_living_41159566",
    "arkit_bedroom_47430034",
    "arkit_bedroom_47895350",
]


@app.function(
    image=mounted(vggt_image),
    volumes=V,
    gpu="L40S",
    timeout=3600,
    max_containers=1,
    secrets=[modal.Secret.from_name("huggingface-secret")],
)
def poses(name: str, method: str) -> dict:
    import noar_eval

    vol.reload()
    if method == "vggt_commercial":
        out = noar_eval.predict_vggt(name)
    else:
        out = noar_eval.predict_mapanything(name)
    vol.commit()
    return out


@app.function(image=mounted(cpu_image), volumes=V, cpu=8, memory=16384, timeout=3600)
def score(name: str, method: str) -> dict:
    import noar_eval

    vol.reload()
    out = noar_eval.score_room(name, method)
    vol.commit()
    return out


@app.function(image=mounted(gpu_image), volumes=V, gpu="L40S", timeout=3600, max_containers=1)
def splat(name: str, which: str, method: str) -> dict:
    import noar_eval
    import splat_gpu

    vol.reload()
    splat_gpu.load_cached_kernels()
    out = noar_eval.splat_room(name, which, method=method)
    vol.commit()
    return out


@app.local_entrypoint()
def main(stage: str = "poses", rooms: str = "", method: str = "mapanything_apache") -> None:
    import json

    names = rooms.split(",") if rooms else ROOMS

    def show(results) -> None:
        for r in results:
            print(json.dumps(r if isinstance(r, dict) else {"failed": repr(r)[:600]}, default=str))

    if stage == "poses":
        show(poses.starmap([(n, method) for n in names], return_exceptions=True))
    elif stage == "score":
        show(score.starmap([(n, method) for n in names], return_exceptions=True))
    elif stage == "splat":
        show(
            splat.starmap(
                [(n, w, method) for n in names for w in ("ar", "fallback")],
                return_exceptions=True,
            )
        )
