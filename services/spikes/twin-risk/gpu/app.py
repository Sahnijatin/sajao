"""Modal app for the Space Twin risk spike. See ../README.md for how to rerun.

    modal run services/spikes/twin-risk/gpu/app.py --stage prep
    modal run services/spikes/twin-risk/gpu/app.py --stage objects
    modal run services/spikes/twin-risk/gpu/app.py --stage splat
    modal run services/spikes/twin-risk/gpu/app.py --stage edit
    modal run services/spikes/twin-risk/gpu/app.py --stage phone

Every job is a local GPU or CPU job on Modal: no hosted model API is called, so
nothing here goes through the model gateway. Internal feasibility testing only.
"""

from __future__ import annotations

from pathlib import Path

import modal

HERE = Path(__file__).resolve().parent
SRC = HERE.parent / "src" / "twin_risk"

ARKIT = {
    "arkit_living_47331265": "47331265",
    "arkit_living_41159541": "41159541",
    "arkit_living_41159566": "41159566",
    "arkit_bedroom_47430034": "47430034",
    "arkit_bedroom_47895350": "47895350",
}
MIP = ["room", "kitchen", "counter"]
REPLICA = ["frl_apartment_0", "apartment_1"]
ALL = [*ARKIT, *MIP, *REPLICA]

# Free-credit budget: never more than three GPU containers per function, no retries.
MAX_GPUS = 3

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
    .add_local_dir(SRC, "/root/twin_risk")
    .add_local_dir(HERE / "twin_gpu", "/root/twin_gpu")
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
    .add_local_dir(SRC, "/root/twin_risk")
    .add_local_dir(HERE / "twin_gpu", "/root/twin_gpu")
)

app = modal.App("sajao-twin-risk-spike")
vol = modal.Volume.from_name("sajao-twin-risk", create_if_missing=True)
V = {"/vol": vol}


@app.function(image=cpu_image, volumes=V, cpu=8, memory=16384, timeout=4 * 3600)
def prep_cpu(kind: str, name: str) -> dict:
    vol.reload()
    from twin_gpu import prep
    from twin_gpu.common import timed

    with timed(name, "prep", "cpu"):
        if kind == "arkit":
            r = prep.prep_arkit(ARKIT[name], name)
        elif kind == "mip":
            r = prep.prep_mip360(name)
        else:
            raise ValueError(kind)
    vol.commit()
    return r


@app.function(image=cpu_image, volumes=V, cpu=16, memory=32768, timeout=6 * 3600)
def replica_cpu(names: list[str]) -> dict:
    vol.reload()
    from twin_gpu import prep
    from twin_gpu.common import timed

    got = prep.fetch_replica(names)
    vol.commit()
    out = {"fetched": got}
    for n in names:
        with timed(n, "prep", "cpu"):
            out[n] = prep.render_replica(n)
        vol.commit()
    return out


@app.function(image=gpu_image, volumes=V, gpu="L40S", timeout=3 * 3600, max_containers=MAX_GPUS)
def objects_gpu(name: str, modes: list[str], detectors: list[str], poses: list[str]) -> dict:
    vol.reload()
    from twin_gpu import objects
    from twin_gpu.common import timed

    res = {}
    for det in detectors:
        objects.set_detector(det)
        with timed(name, f"segment_{det}", "L40S"):
            res[f"segment_{det}"] = objects.segment(name)
        vol.commit()
        for p in poses if modes else []:
            with timed(name, f"objects_{det}_{p}_" + "_".join(modes), "L40S"):
                res[f"metrics_{det}_{p}"] = objects.run_objects(name, modes, p)
            vol.commit()
    return res


@app.function(image=gpu_image, volumes=V, gpu="L40S", timeout=3 * 3600, max_containers=MAX_GPUS)
def splat_gpu(name: str, steps: int = 15000) -> dict:
    vol.reload()
    from twin_gpu import splat
    from twin_gpu.common import timed

    with timed(name, "splat_train", "L40S"):
        r = splat.train_scene(name, steps)
    vol.commit()
    return r


@app.function(image=gpu_image, volumes=V, gpu="L40S", timeout=3 * 3600, max_containers=MAX_GPUS)
def edit_gpu(name: str, detector: str) -> dict:
    vol.reload()
    from twin_gpu import edit, objects
    from twin_gpu.common import timed

    objects.set_detector(detector)
    objects.set_poses("refined")  # poses refined during splat training, where available
    with timed(name, "split_and_fill", "L40S"):
        r = edit.run_edit(name)
    vol.commit()
    return r


@app.function(image=gpu_image, volumes=V, gpu="L40S", timeout=3600, max_containers=MAX_GPUS)
def phone_export_gpu(name: str) -> dict:
    vol.reload()
    from twin_gpu import phone
    from twin_gpu.common import timed

    with timed(name, "phone_export", "L40S"):
        r = phone.export_variants(name)
    vol.commit()
    return r


@app.function(image=cpu_image, volumes=V, cpu=8, memory=32768, timeout=3 * 3600)
def phone_compress_cpu(name: str) -> dict:
    vol.reload()
    from twin_gpu import phone
    from twin_gpu.common import timed

    with timed(name, "phone_compress", "cpu"):
        r = phone.compress_variants(name)
        r["light_mesh"] = phone.light_mesh(name)
    vol.commit()
    return r


def _measure(name: str, gpu: str) -> dict:
    vol.reload()
    from twin_gpu import phone
    from twin_gpu.common import timed

    with timed(name, f"phone_measure_{gpu}", gpu):
        r = phone.measure(name, gpu)
    vol.commit()
    return r


@app.function(image=gpu_image, volumes=V, gpu="L4", timeout=3600, max_containers=MAX_GPUS)
def phone_measure_l4(name: str) -> dict:
    return _measure(name, "L4")


@app.function(image=gpu_image, volumes=V, gpu="T4", timeout=3600, max_containers=MAX_GPUS)
def phone_measure_t4(name: str) -> dict:
    return _measure(name, "T4")


@app.function(image=gpu_image, volumes=V, gpu="L40S", timeout=3600, max_containers=MAX_GPUS)
def phone_measure_l40s(name: str) -> dict:
    return _measure(name, "L40S")


@app.function(image=gpu_image, volumes=V, gpu="T4", timeout=1800, max_containers=MAX_GPUS)
def smoke() -> dict:
    """Check the image: library versions, gsplat pinhole and orthographic rendering."""
    import gsplat
    import mapanything  # noqa: F401
    import torch
    import transformers
    import twin_gpu.common  # noqa: F401  (copies cached kernels to local disk)
    from gsplat import rasterization
    from transformers import Sam2Model  # noqa: F401

    n = 1000
    means = torch.rand(n, 3, device="cuda") - 0.5
    quats = torch.nn.functional.normalize(torch.randn(n, 4, device="cuda"), dim=-1)
    scales = torch.full((n, 3), 0.02, device="cuda")
    op = torch.full((n,), 0.9, device="cuda")
    col = torch.rand(n, 3, device="cuda")
    vm = torch.eye(4, device="cuda")[None]
    vm[0, 2, 3] = 2.0
    out = {}
    for model, f in (("pinhole", 200.0), ("ortho", 100.0)):
        k = torch.tensor([[[f, 0, 64], [0, f, 64], [0, 0, 1]]], device="cuda")
        _, a, _ = rasterization(means, quats, scales, op, col, vm, k, 128, 128, camera_model=model)
        out[f"{model}_alpha_mean"] = float(a.mean())
    out.update(
        torch=str(torch.__version__),
        gsplat=str(gsplat.__version__),
        transformers=str(transformers.__version__),
    )
    import shutil

    # Keep the compiled kernels for later jobs (they load from a local copy).
    shutil.copytree("/root/torch_extensions", "/vol/torch_extensions", dirs_exist_ok=True)
    vol.commit()
    return out


def _scenes(scenes: str) -> list[str]:
    return ALL if scenes == "all" else [s for s in scenes.split(",") if s]


@app.local_entrypoint()
def main(
    stage: str,
    scenes: str = "all",
    steps: int = 15000,
    detectors: str = "gdino,yoloe",
    poses: str = "raw",
) -> None:
    import json

    names = _scenes(scenes)
    dets = [d for d in detectors.split(",") if d]
    calls = []
    if stage == "smoke":
        print(json.dumps(smoke.remote()))
        return
    if stage == "prep":
        for n in names:
            if n in ARKIT:
                calls.append(prep_cpu.spawn("arkit", n))
            elif n in MIP:
                calls.append(prep_cpu.spawn("mip", n))
        reps = [n for n in names if n in REPLICA]
        if reps:
            calls.append(replica_cpu.spawn(reps))
    elif stage == "objects":
        for n in names:
            modes = ["lidar", "mapanything"] if n in ARKIT else []
            calls.append(objects_gpu.spawn(n, modes, dets, poses.split(",")))
    elif stage == "splat":
        calls = [splat_gpu.spawn(n, steps) for n in names]
    elif stage == "edit":
        calls = [edit_gpu.spawn(n, dets[0]) for n in names]
    elif stage == "phone":
        for r in phone_export_gpu.map(names, return_exceptions=True):
            print(json.dumps(r, default=str)[:2000])
        for r in phone_compress_cpu.map(names, return_exceptions=True):
            print(json.dumps(r, default=str)[:2000])
        for fn in (phone_measure_l40s, phone_measure_l4, phone_measure_t4):
            for r in fn.map(names, return_exceptions=True):
                print(json.dumps(r, default=str)[:2000])
        return
    else:
        raise SystemExit(f"unknown stage {stage}")
    for c in calls:
        try:
            print(json.dumps(c.get(), default=str)[:3000], flush=True)
        except Exception as exc:  # report and continue with the other scenes
            print(f"FAILED: {exc!r}", flush=True)
