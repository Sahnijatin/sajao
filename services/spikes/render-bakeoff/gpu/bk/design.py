"""Hand-placed bake-off designs -> render items, plus planted errors for checker calibration.

A room file (/bk/designs/<room>.json, also in eval/render-bakeoff/designs/) holds the
hero keyframe, the clearing sets and three designs. Every item names a listing,
a tier, a position (m, space frame) and a rotation; sizes come from the listing.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

BK = Path("/bk")
MESH_MODEL = "triposg"  # the render-ready asset source for this run


def _listing(lid: str) -> dict:
    for f in (BK / "listings" / "listings.json", BK / "extras" / "listings.json"):
        if f.exists():
            for x in json.loads(f.read_text()):
                if x["id"] == lid:
                    return x
    raise KeyError(lid)


def _cutout_texture(lid: str, out: Path, kind: str) -> tuple[str, float]:
    """Crop a listing photo to its product (alpha kept for billboards). Returns path and aspect w/h."""
    import cv2

    root = BK / ("cutouts" if (BK / "cutouts" / lid).exists() else "extras_cutouts") / lid
    views = json.loads((root / "views.json").read_text())
    idx = views["input"] if views["input"] is not None else views["views"][0]["index"]
    rgba = cv2.imread(str(root / f"{idx}.png"), cv2.IMREAD_UNCHANGED)
    a = rgba[..., 3] > 127
    ys, xs = np.nonzero(a)
    crop = rgba[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]
    if kind != "billboard":
        crop = crop[..., :3]
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), crop)
    return str(out), crop.shape[1] / crop.shape[0]


def render_item(it: dict, tmp: Path) -> dict:
    lst = _listing(it["listing"])
    dims = lst["dims_cm"]
    base = {
        "id": it["id"],
        "listing": lst["id"],
        "name": lst["name"],
        "tier": it["tier"],
        "position": it["position"],
        "rotation_deg": it["rotation_deg"],
        "z": it.get("z", 0.0),
        "category": lst["category"],
    }
    if it["tier"] == "mesh":
        d = BK / "assets" / MESH_MODEL / lst["id"]
        meta = json.loads((d / "asset.json").read_text())
        base.update(
            asset_path=str(d / "asset.ply"),
            front_rot_deg=-meta["front_az_deg"],
            size_m=meta["size_m"],
            scale=it.get("scale", 1.0),
        )
    elif it["tier"] == "rug":
        path, _ = _cutout_texture(lst["id"], tmp / f"{it['id']}.png", "rug")
        lng, wid = dims.get("length") or dims.get("width"), dims.get("width") or dims.get("length")
        base.update(texture_path=path, size_m=[max(lng, wid) / 100, min(lng, wid) / 100, 0.01])
    elif it["tier"] == "art":
        path, aspect = _cutout_texture(lst["id"], tmp / f"{it['id']}.png", "art")
        h = dims.get("height", 50) / 100
        base.update(texture_path=path, size_m=[h * aspect, 0.03, h])
    elif it["tier"] == "billboard":
        path, aspect = _cutout_texture(lst["id"], tmp / f"{it['id']}.png", "billboard")
        h = dims.get("height", 60) / 100 * it.get("scale", 1.0)
        base.update(texture_path=path, size_m=[h * aspect, 0.3, h])
    return base


def load_room(room: str) -> dict:
    return json.loads((BK / "designs" / f"{room}.json").read_text())


def plant_error(items: list[dict], kind: str, room_file: dict) -> list[dict]:
    """Deliberately wrong versions of a design (checker calibration)."""
    items = [dict(x) for x in items]
    meshes = [i for i, x in enumerate(items) if x["tier"] == "mesh"]
    target = max(meshes, key=lambda i: np.prod(items[i]["size_m"])) if meshes else None
    if kind == "swap" and target is not None:
        similar = room_file.get("similar", {}).get(items[target]["listing"])
        if similar:
            items[target] = render_item(
                {**items[target], "listing": similar, "tier": "mesh"}, Path("/tmp/tex")
            )
    elif kind == "scale10" and target is not None:
        items[target]["scale"] = 1.10
        items[target]["size_m"] = [s * 1.1 for s in items[target]["size_m"]]
    elif kind == "move15" and target is not None:
        yaw = math.radians(items[target]["rotation_deg"])
        x, y = items[target]["position"]
        items[target]["position"] = [x + 0.15 * math.cos(yaw), y + 0.15 * math.sin(yaw)]
    elif kind == "plant":
        p = room_file["planted_plant"]
        items.append(render_item({"id": "planted", **p}, Path("/tmp/tex")))
    return items


def load_render_design(room: str, design_id: str, planted: str = "") -> dict:
    rf = load_room(room)
    d = next(x for x in rf["designs"] if x["id"] == design_id)
    tmp = Path("/tmp/tex") / design_id
    items = [render_item(it, tmp) for it in d["items"]]
    if planted:
        items = plant_error(items, planted, rf)
    return {
        "id": design_id,
        "room": room,
        "hero_frame": rf["hero_frame"],
        "variant": d["variant"],
        "render_items": items,
        "slot": d["slot"],
    }
