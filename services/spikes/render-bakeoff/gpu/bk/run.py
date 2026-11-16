"""Per-design orchestration of the generative arms and the checks (runs on the gen image)."""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np

from bakeoff.lock import lock

BK = Path("/bk")


def _read(p: Path) -> np.ndarray:
    import cv2

    return cv2.cvtColor(cv2.imread(str(p), cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)


def _write(p: Path, img: np.ndarray, meta: dict) -> None:
    import cv2

    p.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(p / "image.png"), cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
    (p / "meta.json").write_text(json.dumps(meta, indent=1, default=float))


def _masks(p: Path) -> dict:
    z = np.load(p / "masks.npz")
    return {k: z[k] for k in z.files}


def _ref_cutout(lid: str) -> np.ndarray:
    import cv2

    for root in (BK / "cutouts", BK / "extras_cutouts"):
        if (root / lid).exists():
            v = json.loads((root / lid / "views.json").read_text())
            idx = v["input"] if v["input"] is not None else v["views"][0]["index"]
            rgba = cv2.cvtColor(
                cv2.imread(str(root / lid / f"{idx}.png"), cv2.IMREAD_UNCHANGED),
                cv2.COLOR_BGRA2RGBA,
            )
            a = rgba[..., 3:4].astype(np.float32) / 255
            rgb = rgba[..., :3] * a + 255 * (1 - a)
            ys, xs = np.nonzero(rgba[..., 3] > 127)
            return rgb[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1].astype(np.uint8)
    raise KeyError(lid)


def generate_arms(room: str, design_id: str, model: str, arms: list[str]) -> dict:
    """arms: any of C1 (pass on A), C2 (lock of C1), C3 (pass + lock on the keyframe base), B."""
    from bk import passes
    from bk.checks import Th, item_check
    from bk.design import load_render_design

    base = BK / "renders" / room / design_id
    a_img = _read(base / "A" / "image.png")
    a_m = _masks(base / "A")
    out = {"room": room, "design": design_id, "model": model}
    if "C1" in arms or "C2" in arms:
        t0 = time.time()
        p1, dt = passes.edit(model, [a_img], passes.LIGHT_PROMPT, seed=11)
        _write(base / f"C1_{model}", p1, {"arm": "C1", "model": model, "model_seconds": dt})
        union = a_m["vis"].any(0) if len(a_m["vis"]) else np.zeros(a_img.shape[:2], bool)
        t1 = time.time()
        c2 = lock(a_img, p1, union)
        _write(
            base / f"C2_{model}",
            c2,
            {
                "arm": "C2",
                "model": model,
                "model_seconds": dt,
                "lock_seconds": round(time.time() - t1, 2),
            },
        )
        out["C1_seconds"] = round(time.time() - t0, 1)
    if "C3" in arms:
        c3b = _read(base / "C3base" / "image.png")
        m3 = _masks(base / "C3base")
        p3, dt = passes.edit(model, [c3b], passes.LIGHT_PROMPT, seed=13)
        union = m3["vis"].any(0) if len(m3["vis"]) else np.zeros(c3b.shape[:2], bool)
        _write(base / f"C3pass_{model}", p3, {"arm": "C3pass", "model": model, "model_seconds": dt})
        _write(
            base / f"C3_{model}",
            lock(c3b, p3, union),
            {"arm": "C3", "model": model, "model_seconds": dt},
        )
    if "B" in arms:
        d = load_render_design(room, design_id)
        c3b = _read(base / "C3base" / "image.png")
        m3 = _masks(base / "C3base")
        photo = _read(base / "C3base" / "photo.png")
        refs = {i: _ref_cutout(it["listing"]) for i, it in enumerate(d["render_items"])}
        th = Th()

        def check_item(img, i):
            r = item_check(img, c3b, m3["vis"][i], th)
            if not r.get("present"):
                return True, 0.0, r
            return r["passed"], r["iou"] + r["emb"], r

        t0 = time.time()
        res = passes.arm_b(
            model, photo, m3["region"], d["render_items"], m3["full"], refs, check_item
        )
        _write(
            base / f"B_{model}",
            res["image"],
            {
                "arm": "B",
                "model": model,
                "log": res["log"],
                "model_seconds": res["model_seconds"],
                "total_seconds": round(time.time() - t0, 1),
            },
        )
        out["B_seconds"] = round(time.time() - t0, 1)
    return out


REFERENCE = {"A": "A", "C1": "A", "C2": "A", "C3": "C3base", "B": "C3base"}


def check_arms(room: str, design_id: str, arms: list[str], planted: str = "") -> dict:
    """Check each arm's image against its code-made reference (A, or the C3 base for
    arms that start from the real photo). arms are directory names, e.g. C2_qwen."""
    from bk.checks import check_render

    base = BK / "renders" / room / design_id
    out = {}
    for arm in arms:
        kind = arm.split("_")[0]
        src = BK / "renders" / room / (design_id + (f"__{planted}" if planted else "")) / arm
        if not (src / "image.png").exists():
            out[arm] = {"missing": True}
            continue
        ref_dir = base / REFERENCE[kind]
        ref = _read(ref_dir / "image.png")
        m = _masks(ref_dir)
        final = _read(src / "image.png")
        t0 = time.time()
        r = check_render(final, ref, m["vis"], m["depth"].astype(np.float32), m["region"])
        r["seconds"] = round(time.time() - t0, 1)
        out[arm] = r
        (src / f"checks{'_' + planted if planted else ''}.json").write_text(
            json.dumps(r, indent=1, default=float)
        )
    return out
