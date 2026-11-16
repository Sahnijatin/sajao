"""Parametric category templates: a fourth asset tier for the fidelity gate.

1. A vision model (Claude through the model gateway) looks at the listing photo and
   picks a template and categorical style options. The response schema has no
   numeric fields: the model never sets a size.
2. Code sets every dimension from the listing (width, depth, height) and every
   proportion from fixed rules of those dimensions.
3. Blender builds the mesh from simple parts and exports it (glTF, y up, front +z).
   The gate then projects the real listing photo onto it as texture.
"""

from __future__ import annotations

import json
import math
import time
from pathlib import Path

BK = Path("/bk")
TEMPLATES = ["sofa", "bed", "almirah", "tv_unit", "table", "chair", "shelf"]

OPTIONS: dict[str, list[str]] = {
    "seats": ["1", "2", "3", "4", "n/a"],
    "arms": ["none", "track", "rolled", "slope", "wood", "upholstered", "n/a"],
    "back": ["low", "medium", "high", "slatted", "solid", "n/a"],
    "cushions": ["tight", "loose", "n/a"],
    "legs": [
        "hidden",
        "short_block",
        "straight",
        "tapered",
        "metal",
        "pedestal",
        "trestle",
        "sled",
        "n/a",
    ],
    "headboard": ["none", "panel", "tall_panel", "tufted", "slatted", "n/a"],
    "footboard": ["none", "low", "n/a"],
    "base": ["platform", "legs", "storage_box", "skirted", "raised", "n/a"],
    "doors": ["0", "1", "2", "3", "4", "n/a"],
    "door_style": ["hinged_flat", "hinged_panel", "sliding", "glass", "n/a"],
    "drawers": ["none", "bottom_row", "n/a"],
    "open_shelf": ["yes", "no", "n/a"],
    "top_shape": ["rect", "square", "round", "oval", "n/a"],
    "lower_shelf": ["yes", "no", "n/a"],
    "shelves": ["2", "3", "4", "5", "6", "n/a"],
    "back_panel": ["yes", "no", "n/a"],
    "sides": ["closed", "open_frame", "n/a"],
    "plinth": ["none", "plinth", "legs", "n/a"],
}

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["template", *OPTIONS],
    "properties": {
        "template": {"type": "string", "enum": [*TEMPLATES, "none"]},
        **{k: {"type": "string", "enum": v} for k, v in OPTIONS.items()},
    },
}

PROMPT = (
    "The image is a retailer's product photo of one piece of furniture. Pick the template that fits it "
    "({templates}, or none if no template fits) and the style option that best matches each field. Use "
    "n/a for fields that do not apply to the chosen template. Judge only shape and construction, not "
    "colour or material. Fields: seats and arms and back and cushions (sofas, chairs), headboard, "
    "footboard and base (beds), doors, door_style, drawers, plinth (almirahs, wardrobes, TV units), "
    "open_shelf (TV units), top_shape and lower_shelf (tables), shelves, back_panel and sides (shelves), "
    "legs (all)."
)


# ---------- 1. template choice (vision model via the gateway) ----------


def pick(lid: str) -> dict:
    import asyncio
    import io

    from PIL import Image

    from sajao_gateway import InMemorySpendLedger, ModelGateway, ModelRequest, SpendCaps
    from sajao_gateway.claude import ClaudeProvider, daily_cap_micro_inr
    from sajao_gateway.errors import InvalidOutputError

    views = json.loads((BK / "cutouts" / lid / "views.json").read_text())
    idx = views["input"] if views["input"] is not None else 0
    src = BK / "listings" / lid / f"{idx}.jpg"
    img = Image.open(src).convert("RGB")
    img.thumbnail((1024, 1024))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    cap = daily_cap_micro_inr()
    gw = ModelGateway(
        [ClaudeProvider()],
        ledger=InMemorySpendLedger(
            SpendCaps(per_user_daily_micro_inr=cap, global_daily_micro_inr=cap)
        ),
    )

    def validate(r) -> None:
        j = r.output.get("json") or {}
        if j.get("template") not in [*TEMPLATES, "none"]:
            raise InvalidOutputError("unknown template")

    req = ModelRequest(
        task="asset_template_pick",
        modality="vision",
        prompt_id="asset_template_pick@1",
        payload={
            "prompt": PROMPT.format(templates=", ".join(TEMPLATES)),
            "schema": SCHEMA,
            "effort": "low",
            "max_tokens": 4000,
        },
        blobs=(buf.getvalue(),),
    )
    t0 = time.time()
    resp = asyncio.run(gw.call(req, validate=validate))
    out = {
        "id": lid,
        "spec": resp.output["json"],
        "seconds": round(time.time() - t0, 2),
        "cost_micro_inr": resp.cost_micro_inr,
        "model": resp.model,
        "usage": resp.output.get("usage"),
    }
    d = BK / "assets" / "parametric" / lid
    d.mkdir(parents=True, exist_ok=True)
    (d / "spec.json").write_text(json.dumps(out, indent=1))
    return out


# ---------- 2. dimensions by code ----------


def dims_m(listing: dict, template: str) -> tuple[float, float, float]:
    """(W along x, D along y, H) in metres. Beds run long along y (front is the foot)."""
    d = listing["dims_cm"]
    hs = sorted([v for v in (d.get("width"), d.get("depth"), d.get("length")) if v], reverse=True)
    if not hs:
        hs = [d.get("diameter") or 60] * 2
    if len(hs) == 1:
        hs = hs * 2
    h = (d.get("height") or 75) / 100
    big, small = hs[0] / 100, hs[1] / 100
    if template == "bed":
        return small, big, h
    return big, small, h


# ---------- 3. Blender build ----------


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


class Kit:
    """Adds simple parts in Blender. Blender is z up; the front faces -y (glTF +z after export)."""

    def __init__(self) -> None:
        import bpy

        bpy.ops.wm.read_factory_settings(use_empty=True)
        self.bpy = bpy
        self.parts = []

    def box(self, cx, cy, z0, sx, sy, sz, bevel=0.0):
        bpy = self.bpy
        if min(sx, sy, sz) <= 1e-4:
            return
        bpy.ops.mesh.primitive_cube_add(size=1, location=(cx, cy, z0 + sz / 2))
        ob = bpy.context.active_object
        ob.scale = (sx, sy, sz)
        bpy.ops.object.transform_apply(scale=True)
        if bevel > 0:
            m = ob.modifiers.new("b", "BEVEL")
            m.width = min(bevel, 0.45 * min(sx, sy, sz))
            m.segments = 4
        self.parts.append(ob)

    def cyl(self, cx, cy, z0, r, h, r_top=None, scale_xy=(1.0, 1.0)):
        bpy = self.bpy
        if r_top is None:
            bpy.ops.mesh.primitive_cylinder_add(
                vertices=32, radius=r, depth=h, location=(cx, cy, z0 + h / 2)
            )
        else:
            bpy.ops.mesh.primitive_cone_add(
                vertices=24, radius1=r, radius2=r_top, depth=h, location=(cx, cy, z0 + h / 2)
            )
        ob = bpy.context.active_object
        ob.scale = (scale_xy[0], scale_xy[1], 1)
        bpy.ops.object.transform_apply(scale=True)
        self.parts.append(ob)

    def legs(self, W, D, h, style, inset=0.04, n_x=2):
        if h <= 0.005 or style in ("hidden", "n/a", "none"):
            return
        xs = [-W / 2 + inset + (W - 2 * inset) * i / (n_x - 1) for i in range(n_x)]
        for x in xs:
            for y in (-D / 2 + inset, D / 2 - inset):
                if style == "tapered":
                    self.cyl(x, y, 0, 0.012, h, r_top=0.022)
                elif style == "metal":
                    self.cyl(x, y, 0, 0.008, h)
                elif style == "short_block":
                    self.box(x, y, 0, 0.06, 0.06, h)
                else:
                    self.box(x, y, 0, 0.045, 0.045, h)

    def export(self, path: Path) -> int:
        bpy = self.bpy
        for ob in self.parts:
            ob.select_set(True)
        bpy.context.view_layer.objects.active = self.parts[0]
        for ob in self.parts:
            bpy.context.view_layer.objects.active = ob
            for m in list(ob.modifiers):
                bpy.ops.object.modifier_apply(modifier=m.name)
        bpy.ops.object.select_all(action="SELECT")
        bpy.context.view_layer.objects.active = self.parts[0]
        bpy.ops.object.join()
        path.parent.mkdir(parents=True, exist_ok=True)
        bpy.ops.export_scene.gltf(
            filepath=str(path), export_format="GLB", export_yup=True, export_materials="NONE"
        )
        return len(bpy.context.active_object.data.polygons)


def build_sofa(k: Kit, W, D, H, o):
    leg_h = {
        "hidden": 0.0,
        "short_block": 0.06,
        "straight": 0.10,
        "tapered": 0.13,
        "metal": 0.13,
    }.get(o["legs"], 0.06)
    seat_top = _clamp(0.46, 0.35, 0.6 * H)
    arm_w = {
        "none": 0.0,
        "track": 0.12,
        "rolled": 0.16,
        "slope": 0.14,
        "upholstered": 0.14,
        "wood": 0.07,
    }.get(o["arms"], 0.12)
    arm_w = min(arm_w, 0.12 * W)
    back_t = _clamp(0.2 * D, 0.12, 0.25)
    frame_top = seat_top - 0.13
    k.box(0, 0, leg_h, W, D, frame_top - leg_h, bevel=0.01)  # base frame
    k.box(0, D / 2 - back_t / 2, frame_top, W, back_t, H - frame_top, bevel=0.03)  # back frame
    arm_top = _clamp(seat_top + 0.2, seat_top + 0.08, H - 0.05)
    if arm_w > 0:
        for s in (-1, 1):
            k.box(
                s * (W / 2 - arm_w / 2),
                0,
                leg_h,
                arm_w,
                D,
                arm_top - leg_h,
                bevel=0.06 if o["arms"] in ("rolled",) else 0.015,
            )
    n = int(o["seats"]) if o["seats"].isdigit() else max(1, round((W - 2 * arm_w) / 0.65))
    inner = W - 2 * arm_w
    sd = D - back_t
    loose = o["cushions"] != "tight"
    if loose:
        for i in range(n):
            cx = -inner / 2 + inner * (i + 0.5) / n
            k.box(
                cx,
                -D / 2 + sd / 2,
                frame_top,
                inner / n - 0.01,
                sd - 0.01,
                seat_top - frame_top,
                bevel=0.04,
            )
            k.box(
                cx,
                D / 2 - back_t - 0.08,
                seat_top,
                inner / n - 0.02,
                0.16,
                (H - seat_top) * 0.85,
                bevel=0.05,
            )
    else:
        k.box(0, -D / 2 + sd / 2, frame_top, inner, sd, seat_top - frame_top, bevel=0.02)
    k.legs(W, D, leg_h, o["legs"], n_x=3 if W > 2.0 else 2)


def build_bed(k: Kit, W, D, H, o):
    base = o["base"]
    leg_h = 0.15 if base == "legs" else 0.0
    base_top = {"platform": 0.25, "legs": 0.32, "storage_box": 0.40}.get(base, 0.30)
    hb_t = 0.06
    k.box(0, 0, leg_h, W, D - hb_t, base_top - leg_h, bevel=0.01)
    k.box(0, -hb_t / 2, base_top, W - 0.04, D - hb_t - 0.04, 0.2, bevel=0.05)  # mattress
    hb = o["headboard"]
    hb_top = H if hb in ("tall_panel", "tufted", "panel", "slatted") else base_top + 0.25
    if hb == "slatted":
        n = 8
        for i in range(n + 1):
            k.box(-W / 2 + W * i / n, D / 2 - hb_t / 2, base_top, 0.04, hb_t, hb_top - base_top)
        k.box(0, D / 2 - hb_t / 2, hb_top - 0.06, W, hb_t, 0.06)
        k.box(0, D / 2 - hb_t / 2, 0, W, hb_t, base_top)
    elif hb != "none":
        k.box(0, D / 2 - hb_t / 2, 0, W, hb_t, hb_top, bevel=0.04 if hb == "tufted" else 0.01)
    if o["footboard"] == "low":
        k.box(0, -D / 2 + 0.03, 0, W, 0.05, base_top + 0.12, bevel=0.01)
    k.legs(W, D, leg_h, o["legs"] if base == "legs" else "hidden")


def build_case(k: Kit, W, D, H, o, low: bool = False):
    """Almirah, wardrobe or TV unit: carcass with doors, drawers, open shelf, plinth or legs."""
    foot = o["plinth"]
    if low and o["legs"] not in ("hidden", "n/a"):
        foot = "legs"
    z0 = {"plinth": 0.08, "legs": 0.12}.get(foot, 0.0)
    if foot == "plinth":
        k.box(0, 0.02, 0, W - 0.04, D - 0.04, z0)
    elif foot == "legs":
        k.legs(W, D, z0, "tapered" if low else "straight")
    t = 0.018
    k.box(0, 0, z0, W, D, H - z0)  # carcass
    front_y = -D / 2 - 0.009
    body_h = H - z0
    dr_h = 0.0
    if o["drawers"] == "bottom_row":
        dr_h = min(0.22, body_h * 0.3)
        n_dr = 2 if W > 0.8 else 1
        for i in range(n_dr):
            cx = -W / 2 + W * (i + 0.5) / n_dr
            k.box(cx, front_y, z0 + 0.004, W / n_dr - 0.006, t, dr_h - 0.008)
            k.box(cx, front_y - 0.015, z0 + dr_h * 0.6, 0.12, 0.012, 0.012)
    n = int(o["doors"]) if o["doors"].isdigit() else 2
    open_w = 0.0
    if o["open_shelf"] == "yes" and low:
        open_w = W / (n + 1) if n else W
    door_w_total = W - open_w
    for i in range(n):
        cx = -W / 2 + open_w + door_w_total * (i + 0.5) / n
        k.box(
            cx,
            front_y,
            z0 + dr_h + 0.004,
            door_w_total / n - 0.006,
            t,
            body_h - dr_h - 0.008,
            bevel=0.003 if o["door_style"] == "hinged_panel" else 0.0,
        )
        if o["door_style"] != "sliding":
            hx = cx + (door_w_total / n / 2 - 0.05) * (1 if i % 2 else -1)
            k.box(
                hx,
                front_y - 0.015,
                z0 + dr_h + (body_h - dr_h) * (0.45 if not low else 0.6),
                0.012,
                0.012,
                0.12 if not low else 0.06,
            )
    if open_w > 0:
        k.box(
            -W / 2 + open_w / 2, -D / 2 + 0.05, z0 + dr_h + body_h * 0.45, open_w - 0.04, 0.1, 0.018
        )
    if o["plinth"] == "none" and not low:
        k.box(0, 0, H - 0.03, W + 0.02, D + 0.02, 0.03)  # top lip


def build_table(k: Kit, W, D, H, o):
    top_t = 0.035
    shape = o["top_shape"]
    if shape in ("round", "oval"):
        k.cyl(0, 0, H - top_t, W / 2, top_t, scale_xy=(1.0, D / W if shape == "oval" else 1.0))
    else:
        k.box(0, 0, H - top_t, W, D, top_t, bevel=0.005)
    legs = o["legs"]
    leg_h = H - top_t
    if legs == "pedestal":
        k.cyl(0, 0, 0, 0.06, leg_h)
        k.cyl(0, 0, 0, min(W, D) * 0.3, 0.03)
    elif legs == "trestle":
        for s in (-1, 1):
            k.box(s * (W / 2 - 0.12), 0, 0, 0.05, D * 0.8, leg_h)
    elif legs == "sled":
        for s in (-1, 1):
            k.box(s * (W / 2 - 0.05), 0, 0, 0.03, D * 0.85, 0.03)
            k.box(s * (W / 2 - 0.05), 0, 0, 0.03, 0.03, leg_h)
    else:
        inset = 0.06 if shape not in ("round", "oval") else min(W, D) * 0.22
        k.legs(W, D, leg_h, "tapered" if legs == "tapered" else "straight", inset=inset)
    if o["lower_shelf"] == "yes":
        k.box(0, 0, 0.12, W * 0.85, D * 0.85, 0.02)


def build_chair(k: Kit, W, D, H, o):
    seat_top = _clamp(0.45, 0.3, 0.6 * H)
    lounge = o["back"] in ("high",) and W > 0.65
    seat_t = 0.12 if (o["cushions"] != "n/a" or lounge) else 0.05
    leg_h = seat_top - seat_t
    style = o["legs"]
    if style == "sled":
        for s in (-1, 1):
            k.box(s * (W / 2 - 0.03), 0, 0, 0.025, D, 0.025)
            k.box(s * (W / 2 - 0.03), -D / 2 + 0.05, 0, 0.025, 0.025, leg_h)
    elif style == "hidden":
        k.box(0, 0, 0, W, D, leg_h, bevel=0.01)
    else:
        k.legs(W, D, leg_h, style if style in ("tapered", "metal") else "straight")
    k.box(0, 0, leg_h, W, D, seat_t, bevel=0.02 if seat_t > 0.06 else 0.005)
    back_t = 0.12 if seat_t > 0.06 else 0.03
    if o["back"] == "slatted":
        for i in range(5):
            k.box(
                -W / 2 + 0.05 + (W - 0.1) * i / 4,
                D / 2 - back_t / 2,
                seat_top,
                0.03,
                back_t,
                H - seat_top,
            )
        k.box(0, D / 2 - back_t / 2, H - 0.06, W, back_t, 0.06)
    else:
        k.box(
            0,
            D / 2 - back_t / 2,
            seat_top,
            W,
            back_t,
            H - seat_top,
            bevel=0.02 if back_t > 0.05 else 0.004,
        )
    if o["arms"] in ("wood", "upholstered", "track", "rolled", "slope"):
        aw = 0.05 if o["arms"] == "wood" else 0.12
        for s in (-1, 1):
            k.box(s * (W / 2 - aw / 2), 0, seat_top, aw, D, 0.2, bevel=0.01)


def build_shelf(k: Kit, W, D, H, o):
    t = 0.02
    n = int(o["shelves"]) if o["shelves"].isdigit() else 4
    if o["sides"] == "open_frame":
        for x in (-W / 2 + t, W / 2 - t):
            for y in (-D / 2 + t, D / 2 - t):
                k.box(x, y, 0, 2 * t, 2 * t, H)
    else:
        for s in (-1, 1):
            k.box(s * (W / 2 - t / 2), 0, 0, t, D, H)
    for i in range(n + 1):
        k.box(0, 0, (H - t) * i / n, W, D, t)
    if o["back_panel"] == "yes":
        k.box(0, D / 2 - 0.005, 0, W, 0.01, H)
    if o["doors"].isdigit() and int(o["doors"]) > 0:
        nd = int(o["doors"])
        for i in range(nd):
            k.box(-W / 2 + W * (i + 0.5) / nd, -D / 2 - 0.01, t, W / nd - 0.006, 0.018, H / n - t)


BUILDERS = {
    "sofa": build_sofa,
    "bed": build_bed,
    "almirah": build_case,
    "tv_unit": lambda k, W, D, H, o: build_case(k, W, D, H, o, low=True),
    "table": build_table,
    "chair": build_chair,
    "shelf": build_shelf,
}


def build(lid: str) -> dict:
    """Build the parametric mesh for a listing from its saved spec."""
    from bk.assets import listing

    d = BK / "assets" / "parametric" / lid
    spec = json.loads((d / "spec.json").read_text())["spec"]
    tpl = spec["template"]
    if tpl not in BUILDERS:
        return {"id": lid, "skipped": f"no template ({tpl})"}
    item = listing(lid)
    W, D, H = dims_m(item, tpl)
    t0 = time.time()
    k = Kit()
    BUILDERS[tpl](k, W, D, H, spec)
    faces = k.export(d / "raw.glb")
    meta = {
        "id": lid,
        "model": "parametric",
        "template": tpl,
        "category": item["category"],
        "template_matches_category": tpl == item["category"],
        "size_m": [W, D, H],
        "build_seconds": round(time.time() - t0, 2),
        "faces": faces,
        "textured": False,
        "input_view": json.loads((BK / "cutouts" / lid / "views.json").read_text())["input"],
    }
    (d / "meta.json").write_text(json.dumps(meta, indent=1))
    _ = math
    return meta
