"""Modal app for the product fidelity gate. See ../README.md ("Fidelity gate").

    modal run services/catalog/gpu/app.py::folder --path <product folder>
    modal run services/catalog/gpu/app.py::bakeoff --categories bed,lamp

Scoring (rasterizer, pose search, metrics) is our own numpy code and runs on CPU
containers. The two models run on one shared GPU container: BiRefNet (MIT) cuts the
product out of each photo; DINOv3 embeds images. Internal evaluation and development
only: listing photos stay on private volumes.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import modal

HERE = Path(__file__).resolve().parent
PKG = HERE.parent / "src" / "sajao_catalog"
APP = "sajao-catalog-gate"
CU124 = "https://download.pytorch.org/whl/cu124"
DINOV3 = ("facebook/dinov3-vitl16-pretrain-lvd1689m", "ea8dc2863c51be0a264bab82070e3e8836b02d51")
BIREFNET = ("ZhengPeng7/BiRefNet", "e2bf8e44")

cpu_image = (
    modal.Image.debian_slim(python_version="3.13")
    .pip_install("numpy==2.3.4", "scipy==1.16.3", "trimesh==4.9.0", "pillow==12.0.0")
    .env({"PYTHONPATH": "/root"})
    .add_local_dir(PKG / "gate", "/root/sajao_catalog/gate")
    .add_local_file(PKG / "__init__.py", "/root/sajao_catalog/__init__.py")
)
gpu_image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("torch==2.6.0", "torchvision==0.21.0", index_url=CU124)
    .pip_install(
        "transformers==4.57.1",
        "huggingface_hub==0.35.3",
        "timm==1.0.15",
        "kornia==0.8.1",
        "einops==0.8.1",
        "numpy==1.26.4",
        "pillow==11.2.1",
    )
    .env({"HF_HOME": "/cache/hf"})
)

app = modal.App(APP)
hf_secret = modal.Secret.from_name("huggingface-secret", required_keys=["HF_TOKEN"])
cache = modal.Volume.from_name("sajao-catalog-cache", create_if_missing=True)
catalog = modal.Volume.from_name("sajao-catalog", create_if_missing=True)
bakeoff_vol = modal.Volume.from_name("sajao-render-bakeoff")


@app.cls(
    image=gpu_image,
    gpu=["L4", "A10G"],
    volumes={"/cache": cache},
    secrets=[hf_secret],
    max_containers=1,
    scaledown_window=120,
    timeout=3600,
)
class Models:
    @modal.enter()
    def load(self) -> None:
        import torch
        from transformers import AutoImageProcessor, AutoModel, AutoModelForImageSegmentation

        self.proc = AutoImageProcessor.from_pretrained(DINOV3[0], revision=DINOV3[1])
        self.dino = AutoModel.from_pretrained(DINOV3[0], revision=DINOV3[1]).cuda().eval()
        self.cutter = (
            AutoModelForImageSegmentation.from_pretrained(
                BIREFNET[0], revision=BIREFNET[1], trust_remote_code=True
            )
            .cuda()
            .eval()
            .half()
        )
        torch.set_float32_matmul_precision("high")

    @modal.method()
    def embed(self, pngs: list[bytes]) -> list[list[float]]:
        import torch
        from PIL import Image

        imgs = [Image.open(io.BytesIO(b)).convert("RGB") for b in pngs]
        with torch.no_grad():
            f = self.dino(**self.proc(images=imgs, return_tensors="pt").to("cuda")).pooler_output
        return torch.nn.functional.normalize(f.float(), dim=-1).cpu().tolist()

    @modal.method()
    def cut(self, image: bytes) -> bytes:
        """RGBA PNG with the product's alpha."""
        import numpy as np
        import torch
        import torch.nn.functional as F
        from PIL import Image

        im = Image.open(io.BytesIO(image)).convert("RGB")
        rgb = np.asarray(im)
        h, w = rgb.shape[:2]
        x = torch.from_numpy(rgb).cuda().permute(2, 0, 1)[None].float() / 255
        x = F.interpolate(x, (1024, 1024), mode="bilinear", align_corners=False)
        mean = torch.tensor([0.485, 0.456, 0.406], device="cuda")[:, None, None]
        std = torch.tensor([0.229, 0.224, 0.225], device="cuda")[:, None, None]
        with torch.no_grad():
            a = self.cutter(((x - mean) / std).half())[-1].sigmoid().float()
        a = F.interpolate(a, (h, w), mode="bilinear", align_corners=False)[0, 0].cpu().numpy()
        out = np.dstack([rgb, (a * 255).astype(np.uint8)])
        buf = io.BytesIO()
        Image.fromarray(out).save(buf, "PNG")
        return buf.getvalue()


def _png(a) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.fromarray(a).save(buf, "PNG")
    return buf.getvalue()


def _embedder():
    import numpy as np

    models = Models()

    def embed(imgs):
        return np.array(models.embed.remote([_png(i) for i in imgs]))

    return embed


def _mesh(data: bytes):
    import numpy as np
    import trimesh

    from sajao_catalog.gate.pipeline import Mesh

    s = trimesh.load(io.BytesIO(data), file_type="glb", force="mesh", process=False)
    col = None
    vis = s.visual
    if getattr(vis, "kind", None) == "vertex":
        col = np.asarray(vis.vertex_colors[:, :3], float) / 255
    elif getattr(vis, "kind", None) == "texture":
        col = np.asarray(vis.to_color().vertex_colors[:, :3], float) / 255
    return Mesh(np.asarray(s.vertices, float), np.asarray(s.faces, np.int64), col)


def _rgba(data: bytes):
    import numpy as np
    from PIL import Image

    return np.asarray(Image.open(io.BytesIO(data)).convert("RGBA"))


@app.function(image=cpu_image, cpu=2, memory=4096, timeout=1800, max_containers=24)
def score(
    photos: dict[str, bytes],
    main: str,
    category: str,
    dims_cm: dict[str, float],
    asset: bytes,
    views: list | None = None,
) -> dict:
    """Gate one asset against one product's photos (RGBA cut-outs)."""
    from sajao_catalog.gate.pipeline import gate_product

    imgs = {k: _rgba(v) for k, v in photos.items()}
    sel = (views[0], views[1]) if views else None
    return gate_product(imgs, main, category, dims_cm, _mesh(asset), _embedder(), views=sel)


@app.function(image=cpu_image, cpu=1, timeout=600)
def select(photos: dict[str, bytes], main: str, category: str) -> list:
    from sajao_catalog.gate.pipeline import select_views

    info, keep = select_views({k: _rgba(v) for k, v in photos.items()}, main, category, _embedder())
    return [info, keep]


# ---------- a product folder ----------


@app.local_entrypoint()
def folder(path: str) -> None:
    """<path>/product.json {"category", "dims_cm", "main"}, <path>/photos/*.jpg|png,
    <path>/asset.glb. Writes <path>/gate.json."""
    root = Path(path)
    meta = json.loads((root / "product.json").read_text())
    files = sorted(
        p
        for p in (root / "photos").iterdir()
        if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
    )
    m = Models()
    photos = dict(
        zip([p.stem for p in files], m.cut.map([p.read_bytes() for p in files]), strict=True)
    )
    out = score.remote(
        photos,
        str(meta["main"]),
        meta["category"],
        meta["dims_cm"],
        (root / "asset.glb").read_bytes(),
    )
    (root / "gate.json").write_text(json.dumps(out, indent=1))
    print(f"{root.name}: {out['result']}")


# ---------- evaluation on the bake-off listings ----------


def _bk_photos(lid: str) -> tuple[dict[str, bytes], str | None]:
    cut = Path("/bk/cutouts") / lid
    vf = cut / "views.json"
    if not vf.exists():
        return {}, None
    main = json.loads(vf.read_text()).get("input")
    return {p.stem: p.read_bytes() for p in cut.glob("*.png")}, None if main is None else str(main)


@app.function(image=cpu_image, cpu=1, volumes={"/bk": bakeoff_vol}, timeout=900, max_containers=8)
def bk_select(it: dict) -> dict:
    """Photo selection for one bake-off listing, or why it cannot be gated."""
    from sajao_catalog.gate.pipeline import select_views

    lid = it["id"]
    photos, main = _bk_photos(lid)
    if not (Path("/bk/assets/triposg") / lid / "raw.glb").exists():
        return {**it, "skipped": "no asset (no clean main photo to build one from)"}
    if main is None or main not in photos:
        return {**it, "skipped": "no clean main photo"}
    imgs = {k: _rgba(v) for k, v in photos.items()}
    info, keep = select_views(imgs, main, it["category"], _embedder())
    return {**it, "main": main, "views": [info, keep]}


@app.function(
    image=cpu_image,
    cpu=2,
    memory=4096,
    volumes={"/bk": bakeoff_vol},
    timeout=1800,
    max_containers=24,
)
def bk_score(it: dict, asset_lid: str) -> dict:
    """Gate `asset_lid`'s TripoSG asset against listing `it` (a wrong pair when they differ)."""
    from sajao_catalog.gate.pipeline import gate_product

    photos, _ = _bk_photos(it["id"])
    imgs = {k: _rgba(v) for k, v in photos.items()}
    asset = (Path("/bk/assets/triposg") / asset_lid / "raw.glb").read_bytes()
    info, keep = it["views"]
    return gate_product(
        imgs,
        it["main"],
        it["category"],
        it["dims_cm"],
        _mesh(asset),
        _embedder(),
        views=(info, keep),
    )


@app.local_entrypoint()
def bakeoff(
    listings: str, categories: str = "bed,lamp", wrong: int = 3, out: str = "gate_bakeoff.json"
) -> None:
    """`listings`: the bake-off listings JSON (id, name, category, dims_cm)."""
    cats = set(categories.split(","))
    data = json.loads(Path(listings).read_text())
    items = [
        {k: x.get(k) for k in ("id", "name", "category", "dims_cm")}
        for x in data
        if x["category"] in cats
    ]
    sel = [
        r if not isinstance(r, Exception) else {**it, "skipped": f"error: {r!r}"[:300]}
        for it, r in zip(items, bk_select.map(items, return_exceptions=True), strict=True)
    ]
    ready = [i for i in sel if "skipped" not in i and i["views"][1]]
    jobs = []
    for k, it in enumerate(ready):
        same = [o for o in ready if o["category"] == it["category"] and o["id"] != it["id"]]
        others = [same[(k + j) % len(same)]["id"] for j in range(min(wrong, len(same)))]
        jobs += [(it, a) for a in [it["id"], *others]]
    rows = []
    for (it, aid), r in zip(jobs, bk_score.starmap(jobs, return_exceptions=True), strict=True):
        res = {"error": repr(r)[:300]} if isinstance(r, Exception) else r
        rows.append({"product": it["id"], "asset": aid, "true_pair": it["id"] == aid, **res})
    listed = [
        {k: v for k, v in i.items() if k != "views"}
        | ({"photos": i["views"][0]} if "views" in i else {})
        for i in sel
    ]
    Path(out).write_text(json.dumps({"listings": listed, "rows": rows}, indent=1))
    print(f"{len(ready)} gated of {len(items)}, {len(rows)} scored -> {out}")
