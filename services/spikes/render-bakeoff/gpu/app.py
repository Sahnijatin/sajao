"""Modal app for the render bake-off (SJ-24, SJ-SCOPE-15). See ../README.md.

    M="modal run services/spikes/render-bakeoff/gpu/app.py"
    $M --stage cutouts      # BiRefNet cutouts and clean-view flags for every listing
    $M --stage triposg      # TripoSG mesh per listing
    $M --stage gate --model triposg

Every model runs as a local GPU job on Modal; hosted models (arm B's API model)
are called from the bake-off gateway shim with caps and logging. Internal
evaluation only: listing photos and public datasets are never shipped.
GPU budget: never more than three GPU containers at once across the app.
"""

from __future__ import annotations

import json
from pathlib import Path

import modal

HERE = Path(__file__).resolve().parent
SRC = HERE.parent / "src" / "bakeoff"
TWIN_GPU = HERE.parent.parent / "twin-risk" / "gpu" / "twin_gpu"
TWIN_SRC = HERE.parent.parent / "twin-risk" / "src" / "twin_risk"
# Local paths only matter where the app is defined; inside containers app.py sits in /root.
GATEWAY_SRC = (
    HERE.parents[2] / "gateway" / "src" / "sajao_gateway" if len(HERE.parents) > 2 else HERE
)

MAX_GPUS = 3
CU124 = "https://download.pytorch.org/whl/cu124"
TRIPOSG_REF = "fc5c40990181e2a756c4e0b1c2f4d6b5202faf8c"
TRELLIS2_REF = "75fbf0183001ed9876c8dbb35de6b68552ee08bd"
NVDIFFRAST_REF = "v0.4.0"

bk_vol = modal.Volume.from_name("sajao-render-bakeoff", create_if_missing=True)
twin_vol = modal.Volume.from_name("sajao-twin-risk")


def _base(py: str = "3.11"):
    return (
        modal.Image.from_registry("nvidia/cuda:12.4.1-cudnn-devel-ubuntu22.04", add_python=py)
        .apt_install(
            "git",
            "libgl1",
            "libglib2.0-0",
            "build-essential",
            "clang",
            "libegl1",
            "libgles2",
            "ninja-build",
        )
        .pip_install("torch==2.6.0", "torchvision==0.21.0", index_url=CU124)
        .run_commands(
            "printf 'torch==2.6.0\\ntorchvision==0.21.0\\nnumpy==1.26.4\\n' > /constraints.txt"
        )
        .env(
            {
                "PIP_CONSTRAINT": "/constraints.txt",
                "TORCH_CUDA_ARCH_LIST": "8.6;8.9;9.0",
                "MAX_JOBS": "8",
                "CUDA_HOME": "/usr/local/cuda",
                "CPATH": "/usr/local/cuda/include",
                "FORCE_CUDA": "1",
            }
        )
    )


asset_image = (
    _base()
    .pip_install(
        "numpy==1.26.4",
        "transformers==4.51.3",
        "diffusers==0.33.1",
        "huggingface_hub==0.30.2",
        "accelerate==1.6.0",
        "timm==1.0.15",
        "kornia==0.8.1",
        "einops==0.8.1",
        "opencv-python-headless==4.10.0.84",
        "trimesh==4.6.8",
        "scikit-image==0.25.2",
        "scipy==1.15.2",
        "omegaconf==2.3.0",
        "peft==0.15.2",
        "jaxtyping==0.3.2",
        "typeguard==4.4.2",
        "pymeshlab==2023.12.post3",
        "pillow==11.2.1",
    )
    .run_commands(
        f"pip install --no-build-isolation 'git+https://github.com/NVlabs/nvdiffrast@{NVDIFFRAST_REF}'",
        "pip install --no-build-isolation diso==0.1.4",
        f"git clone https://github.com/VAST-AI-Research/TripoSG /opt/triposg && cd /opt/triposg && git checkout {TRIPOSG_REF}",
    )
    .env({"HF_HOME": "/bk/hf", "PYTHONUNBUFFERED": "1", "PYTHONPATH": "/root"})
    .add_local_dir(SRC, "/root/bakeoff")
    .add_local_dir(HERE / "bk", "/root/bk")
)

# Twin image: the SJ-116 spike's pinned torch and gsplat, plus Blender (bpy) for products.
twin_image = (
    modal.Image.from_registry("nvidia/cuda:12.4.1-cudnn-devel-ubuntu22.04", add_python="3.11")
    .apt_install(
        "git",
        "libgl1",
        "libglib2.0-0",
        "build-essential",
        "clang",
        "libegl1",
        "libxi6",
        "libxxf86vm1",
        "libxfixes3",
        "libxrender1",
        "libxkbcommon0",
        "libsm6",
        "libx11-6",
    )
    .pip_install("torch==2.4.1", "torchvision==0.19.1", index_url=CU124)
    .run_commands(
        "printf 'torch==2.4.1\\ntorchvision==0.19.1\\nnumpy==1.26.4\\n' > /constraints.txt"
    )
    .env(
        {
            "PIP_CONSTRAINT": "/constraints.txt",
            "TORCH_CUDA_ARCH_LIST": "8.6;8.9;9.0",
            "MAX_JOBS": "8",
        }
    )
    .pip_install(
        "numpy==1.26.4", "ninja==1.11.1.3", "jaxtyping==0.2.36", "rich==13.9.4", "packaging==24.2"
    )
    .run_commands("pip install --no-build-isolation gsplat==1.5.3")
    .pip_install(
        "pytorch-msssim==1.0.0",
        "opencv-python-headless==4.10.0.84",
        "scipy==1.15.2",
        "trimesh==4.6.8",
        "pillow==11.2.1",
        "bpy==4.2.0",
    )
    .env(
        {
            "PYTHONUNBUFFERED": "1",
            "PYTHONPATH": "/root",
            "TORCH_EXTENSIONS_DIR": "/root/torch_extensions",
            "OPENCV_IO_ENABLE_OPENEXR": "1",
        }
    )
    .add_local_dir(SRC, "/root/bakeoff")
    .add_local_dir(TWIN_SRC, "/root/twin_risk")
    .add_local_dir(TWIN_GPU, "/root/twin_gpu")
    .add_local_dir(HERE / "bk", "/root/bk")
)

# Generative passes and checks: diffusers (Qwen-Image-Edit-2511, FLUX.2 klein), SAM 2.1, DINOv2,
# Qwen3-VL, YOLOE (AGPL, evaluation only) and MoGe-3.
MOGE_REF = "74fbce054ebed49800de42d0ad0e83495065719a"
gen_image = (
    modal.Image.from_registry("nvidia/cuda:12.8.1-cudnn-devel-ubuntu22.04", add_python="3.11")
    .apt_install("git", "libgl1", "libglib2.0-0", "build-essential")
    .pip_install("torch==2.8.0", "torchvision==0.23.0")
    .run_commands("printf 'torch==2.8.0\\ntorchvision==0.23.0\\n' > /constraints.txt")
    .env({"PIP_CONSTRAINT": "/constraints.txt"})
    .pip_install(
        "diffusers==0.43.0",
        "transformers==5.23.0",
        "accelerate==1.15.0",
        "peft==0.21.3",
        "sentencepiece==0.2.1",
        "opencv-python-headless==4.10.0.84",
        "scipy==1.15.2",
        "pillow==11.2.1",
        "google-genai==1.47.0",
    )
    .pip_install(f"moge @ git+https://github.com/microsoft/MoGe@{MOGE_REF}")
    .pip_install("ultralytics==8.4.214", "git+https://github.com/ultralytics/CLIP.git")
    .env({"HF_HOME": "/bk/hf", "PYTHONUNBUFFERED": "1", "PYTHONPATH": "/root"})
    .add_local_dir(SRC, "/root/bakeoff")
    .add_local_dir(GATEWAY_SRC, "/root/sajao_gateway")
    .add_local_dir(HERE / "bk", "/root/bk")
)

hf_secret = modal.Secret.from_name("huggingface-secret", required_keys=["HF_TOKEN"])
gcp_secret = modal.Secret.from_name("gcp", required_keys=["GCP_SA_KEY"])

TRELLIS_DEPS = {  # pinned commits of TRELLIS.2's CUDA extensions
    "FlexGEMM": "6dd94a859c26",
    "CuMesh": "12289e1062f0",
}
trellis_image = (
    _base()
    .apt_install("libeigen3-dev")
    .env({"CPATH": "/usr/local/cuda/include:/usr/include/eigen3"})
    .pip_install("xformers==0.0.29.post3", index_url=CU124)
    .pip_install(
        "numpy==1.26.4",
        "transformers==4.57.1",
        "huggingface_hub==0.35.3",
        "imageio==2.37.0",
        "imageio-ffmpeg==0.6.0",
        "tqdm==4.67.1",
        "easydict==1.13",
        "opencv-python-headless==4.10.0.84",
        "trimesh==4.6.8",
        "scipy==1.15.2",
        "pillow==11.2.1",
        "kornia==0.8.1",
        "timm==1.0.15",
        "zstandard==0.23.0",
        "lpips==0.1.4",
        "pandas==2.2.3",
        "git+https://github.com/EasternJournalist/utils3d.git@9a4eb15e4021b67b12c460c7057d642626897ec8",
    )
    .run_commands(
        f"git clone https://github.com/microsoft/TRELLIS.2 /opt/trellis2 && cd /opt/trellis2 && git checkout {TRELLIS2_REF} && git submodule update --init --recursive",
        f"pip install --no-build-isolation 'git+https://github.com/NVlabs/nvdiffrast@{NVDIFFRAST_REF}'",
        "git clone -b renderutils https://github.com/JeffreyXiang/nvdiffrec.git /tmp/nvdiffrec && pip install --no-build-isolation /tmp/nvdiffrec",
        f"git clone --recursive https://github.com/JeffreyXiang/FlexGEMM /tmp/FlexGEMM && cd /tmp/FlexGEMM && git checkout {TRELLIS_DEPS['FlexGEMM']} && git submodule update --init --recursive && pip install --no-build-isolation .",
        f"git clone --recursive https://github.com/JeffreyXiang/CuMesh /tmp/CuMesh && cd /tmp/CuMesh && git checkout {TRELLIS_DEPS['CuMesh']} && git submodule update --init --recursive && pip install --no-build-isolation .",
        "cp -r /opt/trellis2/o-voxel /tmp/o-voxel && pip install --no-build-isolation /tmp/o-voxel",
    )
    .env(
        {
            "HF_HOME": "/bk/hf",
            "PYTHONUNBUFFERED": "1",
            "PYTHONPATH": "/root:/opt/trellis2",
            "ATTN_BACKEND": "xformers",
            "SPARSE_ATTN_BACKEND": "xformers",
            "OPENCV_IO_ENABLE_OPENEXR": "1",
        }
    )
    .add_local_dir(SRC, "/root/bakeoff")
    .add_local_dir(HERE / "bk", "/root/bk")
)

SAM3D_REF = "f91db411c50e"
sam3d_image = (
    modal.Image.from_registry("nvidia/cuda:12.1.1-cudnn8-devel-ubuntu22.04", add_python="3.11")
    .apt_install(
        "git",
        "libgl1",
        "libglib2.0-0",
        "build-essential",
        "clang",
        "ninja-build",
        "libegl1",
        "libxi6",
        "libxrender1",
        "libxkbcommon0",
        "libsm6",
        "libx11-6",
        "libxxf86vm1",
        "libxfixes3",
    )
    .pip_install(
        "torch==2.5.1", "torchvision==0.20.1", index_url="https://download.pytorch.org/whl/cu121"
    )
    .env(
        {
            "TORCH_CUDA_ARCH_LIST": "8.0;8.6;8.9;9.0",
            "MAX_JOBS": "8",
            "CUDA_HOME": "/usr/local/cuda",
            "CPATH": "/usr/local/cuda/include",
            "FORCE_CUDA": "1",
        }
    )
    .run_commands(
        f"git clone https://github.com/facebookresearch/sam-3d-objects /opt/sam3d && cd /opt/sam3d && git checkout {SAM3D_REF}",
        # nvidia-pyindex only registers NVIDIA's package index, which the builders cannot reach.
        "cd /opt/sam3d && sed -i '/nvidia-pyindex/d' requirements*.txt pyproject.toml",
        "cd /opt/sam3d && PIP_EXTRA_INDEX_URL='https://download.pytorch.org/whl/cu121' pip install -e '.[dev]'",
        "cd /opt/sam3d && PIP_EXTRA_INDEX_URL='https://download.pytorch.org/whl/cu121' pip install --no-build-isolation -e '.[p3d]'",
        "cd /opt/sam3d && PIP_FIND_LINKS='https://nvidia-kaolin.s3.us-east-2.amazonaws.com/torch-2.5.1_cu121.html' pip install -e '.[inference]'",
        "cd /opt/sam3d && bash ./patching/hydra || true",
    )
    .env({"HF_HOME": "/bk/hf", "PYTHONUNBUFFERED": "1", "PYTHONPATH": "/root"})
    .add_local_dir(SRC, "/root/bakeoff")
    .add_local_dir(HERE / "bk", "/root/bk")
)

anthropic_secret = modal.Secret.from_name("anthropic-secret", required_keys=["ANTHROPIC_API_KEY"])
claude_image = (
    modal.Image.debian_slim(python_version="3.13")
    .pip_install("anthropic==2.8.0", "pillow==11.2.1", "numpy==2.2.6")
    .env({"PYTHONUNBUFFERED": "1", "PYTHONPATH": "/root"})
    .add_local_dir(GATEWAY_SRC, "/root/sajao_gateway")
    .add_local_dir(SRC, "/root/bakeoff")
    .add_local_dir(HERE / "bk", "/root/bk")
)

app = modal.App("sajao-render-bakeoff")
# The gated 3D models build heavy images; a separate app keeps their builds from
# blocking every other stage.
gated = modal.App("sajao-render-bakeoff-gated")
VOLS = {"/bk": bk_vol}
TWIN_VOLS = {"/bk": bk_vol, "/vol": twin_vol}
ROOMS = [
    "arkit_living_47331265",
    "arkit_living_41159541",
    "arkit_living_41159566",
    "arkit_bedroom_47430034",
    "arkit_bedroom_47895350",
    "frl_apartment_0",
    "apartment_1",
]


@app.function(image=twin_image, gpu="L4", volumes=TWIN_VOLS, timeout=1800, max_containers=1)
def survey(room: str) -> dict:
    from bk.twin import survey as run

    r = run(room)
    bk_vol.commit()
    return r


@app.function(image=twin_image, gpu="L40S", volumes=TWIN_VOLS, timeout=3600, max_containers=1)
def clear(room: str, ids: list[int], tag: str) -> dict:
    from bk.twin import clear_zone

    r = clear_zone(room, ids, tag)
    bk_vol.commit()
    return r


@app.function(image=asset_image, gpu="L4", volumes=VOLS, timeout=3600, max_containers=MAX_GPUS)
def cutouts(lids: list[str]) -> list[dict]:
    from bk.assets import make_cutouts

    out = [make_cutouts(lid) for lid in lids]
    bk_vol.commit()
    return out


@app.function(image=asset_image, gpu="L40S", volumes=VOLS, timeout=3600, max_containers=2)
def triposg(lids: list[str]) -> list[dict]:
    from bk.assets import run_triposg

    out = []
    for lid in lids:
        try:
            out.append(run_triposg(lid))
        except Exception as e:
            out.append({"id": lid, "error": repr(e)[:400]})
        bk_vol.commit()
    return out


@gated.function(
    image=trellis_image,
    gpu="H100",
    volumes=VOLS,
    timeout=3600,
    max_containers=2,
    secrets=[hf_secret],
)
def trellis2(lids: list[str]) -> list[dict]:
    from bk.assets import run_trellis2

    out = []
    for lid in lids:
        try:
            out.append(run_trellis2(lid))
        except Exception:
            import traceback

            out.append({"id": lid, "error": traceback.format_exc()[-1200:]})
        bk_vol.commit()
    return out


@gated.function(
    image=sam3d_image, gpu="H100", volumes=VOLS, timeout=3600, max_containers=2, secrets=[hf_secret]
)
def sam3d(lids: list[str]) -> list[dict]:
    from bk.assets import run_sam3d

    out = []
    for lid in lids:
        try:
            out.append(run_sam3d(lid))
        except Exception:
            import traceback

            out.append({"id": lid, "error": traceback.format_exc()[-1200:]})
        bk_vol.commit()
    return out


@app.function(
    image=gen_image,
    gpu="L4",
    volumes=TWIN_VOLS,
    timeout=3600,
    max_containers=MAX_GPUS,
    secrets=[gcp_secret, hf_secret],
)
def generate_gemini(room: str, design_id: str, arms: list[str]) -> dict:
    """Arm B with Gemini on Vertex AI (through the gateway). The GPU runs the item checks."""
    from bk.run import generate_arms

    bk_vol.reload()
    r = generate_arms(room, design_id, "gemini", arms)
    bk_vol.commit()
    return r


@app.function(
    image=claude_image, volumes=VOLS, timeout=1800, max_containers=4, secrets=[anthropic_secret]
)
def pick_templates(lids: list[str]) -> list[dict]:
    """Parametric tier, step 1: the vision model picks template and options (no sizes)."""
    from bk.parametric import pick

    out = []
    for lid in lids:
        try:
            out.append(pick(lid))
        except Exception as e:
            out.append({"id": lid, "error": repr(e)[:600]})
        bk_vol.commit()
    return out


@app.function(image=twin_image, volumes=VOLS, timeout=1800, max_containers=4, cpu=4)
def build_parametric(lids: list[str]) -> list[dict]:
    """Parametric tier, step 2: code sets the sizes, Blender builds and exports the mesh (CPU)."""
    from bk.parametric import build

    out = []
    for lid in lids:
        try:
            out.append(build(lid))
        except Exception:
            import traceback

            out.append({"id": lid, "error": traceback.format_exc()[-1200:]})
        bk_vol.commit()
    return out


@app.function(image=asset_image, gpu="L4", volumes=VOLS, timeout=3600, max_containers=MAX_GPUS)
def gate(model: str, jobs: list[tuple[str, list[str]]]) -> list[dict]:
    from bk.fidelity import gate_listing

    out = []
    for lid, against in jobs:
        try:
            out.append(gate_listing(model, lid, against))
        except Exception:
            import traceback

            out.append({"id": lid, "model": model, "error": traceback.format_exc()[-1500:]})
        bk_vol.commit()
    return out


@app.function(image=asset_image, gpu="L4", volumes=VOLS, timeout=3600, max_containers=MAX_GPUS)
def prepare_assets(model: str, lids: list[str]) -> list[dict]:
    from bk.fidelity import prepare_asset

    out = []
    for lid in lids:
        try:
            out.append(prepare_asset(model, lid))
        except Exception as e:
            out.append({"id": lid, "error": repr(e)[:400]})
        bk_vol.commit()
    return out


@app.function(
    image=twin_image, gpu="L40S", volumes=TWIN_VOLS, timeout=3600, max_containers=MAX_GPUS
)
def compose(room: str, design_id: str, planted: str = "") -> dict:
    """Arm A (splat background) and the C3 base (keyframe background) for one design."""
    import json as _j

    from bk.compose import composite
    from bk.design import load_render_design

    bk_vol.reload()
    d = load_render_design(room, design_id, planted)
    base = Path("/bk/renders") / room / (design_id + (f"__{planted}" if planted else ""))
    out = {"A": composite(room, d, d["hero_frame"], d["variant"], "splat", out=base / "A")}
    if not planted:
        out["C3base"] = composite(
            room, d, d["hero_frame"], d["variant"], "keyframe", out=base / "C3base"
        )
    bk_vol.commit()
    return _j.loads(_j.dumps(out, default=float))


@app.function(
    image=gen_image,
    gpu="H100",
    volumes=TWIN_VOLS,
    timeout=3600,
    max_containers=MAX_GPUS,
    secrets=[
        modal.Secret.from_dict({"PYTORCH_CUDA_ALLOC_CONF": "expandable_segments:True"}),
        hf_secret,
    ],
)
def generate(room: str, design_id: str, model: str, arms: list[str]) -> dict:
    from bk.run import generate_arms

    bk_vol.reload()
    r = generate_arms(room, design_id, model, arms)
    bk_vol.commit()
    return r


@app.function(image=gen_image, gpu="L40S", volumes=TWIN_VOLS, timeout=3600, max_containers=MAX_GPUS)
def check(room: str, design_id: str, arms: list[str], planted: str = "") -> dict:
    from bk.run import check_arms

    bk_vol.reload()
    r = check_arms(room, design_id, arms, planted)
    bk_vol.commit()
    return r


def _chunks(xs, n):
    k = max(1, (len(xs) + n - 1) // n)
    return [xs[i : i + k] for i in range(0, len(xs), k)]


def _listings(extras: bool = False) -> list[dict]:
    d = Path(__file__).resolve().parents[4] / "eval" / "render-bakeoff"
    out = json.loads((d / "listings.json").read_text()) if (d / "listings.json").exists() else []
    if extras and (d / "extras.json").exists():
        out += json.loads((d / "extras.json").read_text())
    return out


def _room_files() -> dict:
    d = Path(__file__).resolve().parents[4] / "eval" / "render-bakeoff" / "designs"
    return {
        f.stem: json.loads(f.read_text())
        for f in sorted(d.glob("*.json"))
        if not f.stem.endswith(".designs")
    }


PLANTED = ["swap", "scale10", "move15", "plant"]
ARMS_OPEN = ["C1", "C2", "C3", "B"]


@app.local_entrypoint()
def main(stage: str, model: str = "triposg", only: str = "", limit: int = 0, gen: str = "qwen"):
    import random

    out_dir = Path(__file__).resolve().parents[4] / "eval" / "render-bakeoff" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    rooms = _room_files()
    if only and stage in ("clear", "compose", "generate", "check", "plant", "pilot"):
        rooms = {
            k: v
            for k, v in rooms.items()
            if k in only.split(",") or any(d["id"] in only.split(",") for d in v["designs"])
        }
    jobs = [
        (r, d["id"])
        for r, rf in rooms.items()
        for d in rf["designs"]
        if not only or r in only.split(",") or d["id"] in only.split(",")
    ]
    if stage == "clear":
        args = [(r, rf["clear"]["zone"], "zone") for r, rf in rooms.items()]
        res = list(clear.starmap(args, return_exceptions=True))
        (out_dir / "clear.json").write_text(json.dumps(res, indent=1, default=str))
        print(res)
        return
    if stage == "compose":
        res = list(compose.starmap(jobs, return_exceptions=True))
        (out_dir / "compose.json").write_text(json.dumps(res, indent=1, default=str))
        print(json.dumps(res, default=str)[:3000])
        return
    if stage == "plant":
        pj = [(r, d, p) for r, d in jobs for p in PLANTED]
        res = list(compose.starmap(pj, return_exceptions=True))
        (out_dir / "plant_compose.json").write_text(json.dumps(res, indent=1, default=str))
        cj = [(r, d, ["A"], p) for r, d, p in pj]
        res = list(check.starmap(cj, return_exceptions=True))
        (out_dir / "plant_checks.json").write_text(json.dumps(res, indent=1, default=str))
        return
    if stage == "pilot":
        res = list(
            generate.starmap(
                [(r, d, m, ["C1", "C2"]) for r, d in jobs for m in ("qwen", "flux2k")],
                return_exceptions=True,
            )
        )
        print(json.dumps(res, default=str)[:3000])
        return
    if stage == "generate":
        res = list(
            generate.starmap([(r, d, gen, ARMS_OPEN) for r, d in jobs], return_exceptions=True)
        )
        (out_dir / f"generate_{gen}.json").write_text(json.dumps(res, indent=1, default=str))
        print(json.dumps(res, default=str)[:3000])
        return
    if stage == "check":
        arms = ["A", f"C1_{gen}", f"C2_{gen}", f"C3_{gen}", f"B_{gen}"]
        res = list(check.starmap([(r, d, arms) for r, d in jobs], return_exceptions=True))
        (out_dir / f"checks_{gen}.json").write_text(json.dumps(res, indent=1, default=str))
        return
    if stage == "prepare":
        lids = only.split(",") if only else [x["id"] for x in _listings()]
        res = [
            r for rs in prepare_assets.map([model] * MAX_GPUS, _chunks(lids, MAX_GPUS)) for r in rs
        ]
        (out_dir / f"prepare_{model}.json").write_text(json.dumps(res, indent=1, default=float))
        print(sum(1 for r in res if "error" in r), "errors of", len(res))
        return
    if stage == "survey":
        rooms = [r for r in (only.split(",") if only else ROOMS)]
        for r in survey.map(rooms, return_exceptions=True):
            print(r)
        return
    items = _listings(extras=stage == "cutouts")
    if only:
        items = [x for x in items if x["id"] in only.split(",")]
    if limit:
        items = items[:limit]
    lids = [x["id"] for x in items]
    if stage == "cutouts":
        res = [r for rs in cutouts.map(_chunks(lids, MAX_GPUS)) for r in rs]
        (out_dir / "cutouts.json").write_text(json.dumps(res, indent=1))
        print(sum(1 for r in res if r["clean"]), "of", len(res), "listings have a clean view")
    elif stage == "triposg":
        res = [r for rs in triposg.map(_chunks(lids, 2)) for r in rs]
        (out_dir / "assets_triposg.json").write_text(json.dumps(res, indent=1))
        print(res[:3])
    elif stage == "gate":
        rng = random.Random(7)
        by_cat: dict[str, list[str]] = {}
        for x in _listings():
            by_cat.setdefault(x["category"], []).append(x["id"])
        jobs = []
        for x in items:
            others = [o for o in by_cat[x["category"]] if o != x["id"]]
            jobs.append((x["id"], rng.sample(others, min(2, len(others)))))
        gj = jobs
        res = [r for rs in gate.map([model] * MAX_GPUS, _chunks(gj, MAX_GPUS)) for r in rs]
        (out_dir / f"gate_{model}.json").write_text(json.dumps(res, indent=1, default=float))
        print(sum(1 for r in res if "error" in r), "errors of", len(res))
    else:
        raise SystemExit(f"unknown stage {stage}")
