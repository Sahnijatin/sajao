"""Room understanding for design: what the design engine and the render read.

For each thing in the twin: its footprint on the floor plan, whether a redesign
keeps it or may replace it, and its mask in each hero photo (for taking it out
of that photo). For the room: the free floor a redesign can use.

Every function here is pure. `understand_room` and `attach_hero_masks` take and
return a SpaceTwin (validated both ways); `hero_mask_plan` works in the frames'
world on the objects step's output. No model sets a size or a position: they
come from the fused geometry, with its error bands.
"""

import copy
import math
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
from PIL import Image, ImageDraw

from sajao_schemas.generated.v1 import SpaceTwin

# A thing other than furniture stands on the floor when its box's bottom is this
# close to it (plus the height band). Furniture always does, whatever was seen of it.
FLOOR_TOUCH_M = 0.10
# Furniture named like this hangs on a wall.
OFF_FLOOR_WORDS = ("wall", "hanging", "mounted")
# Kept by default: fixed fittings a redesign works around.
KEEP_TYPES = {"fixture"}
# Free floor is counted on a grid this fine.
GRID_M = 0.02
# A hero view gets a mask only when at least this share of the thing is in frame and in sight.
MIN_VISIBLE = 0.3
# A box sample is hidden when the depth there is nearer than it by more than this.
OCCLUSION_M = 0.15


def _validated(twin: Mapping[str, Any]) -> dict[str, Any]:
    SpaceTwin.model_validate(twin)
    return dict(twin)


def footprint(box: Mapping[str, Any], kind: str | None = None, name: str = "") -> dict[str, Any]:
    """A box seen from above (space frame, z up): its corners, its sizes and whether it
    stands on the floor.

    Boxes cover only what was seen, so a chair seen over a table starts in mid-air:
    furniture stands on the floor unless its name says it hangs; wall items never
    do; anything else does when its box reaches down to the floor."""
    c = box["center"]
    yaw = math.radians(float(box["yaw_deg"]))
    w, d = box["width"]["value_m"], box["depth"]["value_m"]
    du, dv = (math.cos(yaw), math.sin(yaw)), (-math.sin(yaw), math.cos(yaw))
    polygon = [
        {
            "x_m": round(c["x_m"] + su * w / 2 * du[0] + sv * d / 2 * dv[0], 4),
            "y_m": round(c["y_m"] + su * w / 2 * du[1] + sv * d / 2 * dv[1], 4),
        }
        for su, sv in ((-1, -1), (1, -1), (1, 1), (-1, 1))
    ]
    height = box["height"]
    bottom = c["z_m"] - height["value_m"] / 2
    if kind == "furniture":
        on_floor = not any(word in name.lower() for word in OFF_FLOOR_WORDS)
    elif kind == "wall_item":
        on_floor = False
    else:
        on_floor = bottom <= FLOOR_TOUCH_M + height["error_band_m"]
    return {
        "polygon": polygon,
        "width": dict(box["width"]),
        "depth": dict(box["depth"]),
        "on_floor": on_floor,
    }


def _area(polygon: Sequence[Mapping[str, float]]) -> float:
    pts = [(p["x_m"], p["y_m"]) for p in polygon]
    return (
        abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(pts, [*pts[1:], pts[0]], strict=True)))
        / 2
    )


def _perimeter(polygon: Sequence[Mapping[str, float]]) -> float:
    pts = [(p["x_m"], p["y_m"]) for p in polygon]
    return sum(math.dist(a, b) for a, b in zip(pts, [*pts[1:], pts[0]], strict=True))


def free_floor(twin: Mapping[str, Any]) -> dict[str, Any]:
    """The floor polygon less the on-floor footprints of kept objects and built-ins.

    The floor area is exact; the share left free is counted on a 2 cm grid. The band
    is first order: a length's band covers both its ends, so it is half the
    perimeter times that band (the largest wall band for the floor, each
    footprint's larger side band for it)."""
    shell = twin["shell"]
    floor = shell["floor_polygon"]
    xs, ys = [p["x_m"] for p in floor], [p["y_m"] for p in floor]
    x0, y0 = min(xs), min(ys)
    size = (
        math.ceil((max(xs) - x0) / GRID_M) + 1,
        math.ceil((max(ys) - y0) / GRID_M) + 1,
    )

    def px(polygon: Sequence[Mapping[str, float]]) -> list[tuple[float, float]]:
        return [((p["x_m"] - x0) / GRID_M, (p["y_m"] - y0) / GRID_M) for p in polygon]

    image = Image.new("1", size, 0)
    draw = ImageDraw.Draw(image)
    draw.polygon(px(floor), fill=1)
    floor_cells = int(np.asarray(image).sum())

    kept = [o for o in twin["objects"] if o.get("redesign", {}).get("state") == "keep"] + list(
        shell.get("built_ins", [])
    )
    kept = [k for k in kept if k.get("footprint", {}).get("on_floor")]
    band = 0.0
    for thing in kept:
        fp = thing["footprint"]
        draw.polygon(px(fp["polygon"]), fill=0)
        side_band = max(fp["width"]["error_band_m"], fp["depth"]["error_band_m"])
        band += _perimeter(fp["polygon"]) / 2 * side_band
    wall_band = max((w["length"]["error_band_m"] for w in shell["walls"]), default=0.0)
    band += _perimeter(floor) / 2 * wall_band
    # The grid counts edge cells whole; the share it gives does not depend on that.
    area = _area(floor)
    free_share = int(np.asarray(image).sum()) / floor_cells if floor_cells else 0.0
    return {
        "area_m2": round(area * free_share, 3),
        "error_band_m2": round(band, 3),
        "floor_area_m2": round(area, 3),
        "kept_ids": [k["id"] for k in kept],
    }


def understand_room(twin: Mapping[str, Any]) -> dict[str, Any]:
    """Footprints, keep or replace, and free floor, added to a SpaceTwin.

    A person's choice (`redesign.source` user) is kept; otherwise the rule sets
    it: fixtures keep, everything else may be replaced. The input is not changed."""
    out = copy.deepcopy(_validated(twin))
    for obj in out["objects"]:
        kind = obj.get("object_type", "furniture")
        obj["footprint"] = footprint(obj["box"], kind, obj["category"])
        if obj.get("redesign", {}).get("source") != "user":
            kind = obj.get("object_type", "furniture")
            obj["redesign"] = {
                "state": "keep" if kind in KEEP_TYPES else "replace",
                "source": "rule",
            }
    for built_in in out["shell"].get("built_ins", []):
        built_in["footprint"] = footprint(built_in["box"], "built_in", built_in["category"])
    out["free_floor"] = free_floor(out)
    return _validated(out)


def _samples(box: Mapping[str, Any], up: int) -> tuple[np.ndarray, np.ndarray]:
    """Points inside a world box (3 by 3 by 3, shrunk to 80%) and its 8 corners."""
    a, b = [i for i in range(3) if i != up]
    c = np.asarray(box["center"], dtype=np.float64)
    yaw = math.radians(float(box["yaw_deg"]))
    ln, wd, ht = (box[k]["value_m"] for k in ("length", "width", "height"))

    def point(u: float, v: float, z: float) -> np.ndarray:
        p = c.copy()
        p[a] += u * math.cos(yaw) - v * math.sin(yaw)
        p[b] += u * math.sin(yaw) + v * math.cos(yaw)
        p[up] += z
        return p

    steps = (-0.4, 0.0, 0.4)
    inside = np.array([point(i * ln, j * wd, k * ht) for i in steps for j in steps for k in steps])
    corners = np.array(
        [
            point(i * ln, j * wd, k * ht)
            for i in (-0.5, 0.5)
            for j in (-0.5, 0.5)
            for k in (-0.5, 0.5)
        ]
    )
    return inside, corners


def _project(points: np.ndarray, frame: Mapping[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    w2c = np.linalg.inv(np.asarray(frame["c2w"], dtype=np.float64))
    cam = points @ w2c[:3, :3].T + w2c[:3, 3]
    k = np.asarray(frame["intrinsics"], dtype=np.float64)
    z = cam[:, 2]
    safe = np.where(z > 1e-6, z, 1e-6)
    uv = np.stack(
        [k[0, 0] * cam[:, 0] / safe + k[0, 2], k[1, 1] * cam[:, 1] / safe + k[1, 2]], axis=1
    )
    return uv, z


def visible_share(
    box: Mapping[str, Any], up: int, frame: Mapping[str, Any], depth: np.ndarray
) -> float:
    """Share of a box's inside samples that are in frame and not behind a nearer surface."""
    inside, _ = _samples(box, up)
    uv, z = _project(inside, frame)
    h, w = depth.shape
    seen = 0
    for (u, v), dist in zip(uv, z, strict=True):
        if dist <= 0.1 or not (0 <= u < w and 0 <= v < h):
            continue
        measured = float(depth[int(v), int(u)])
        if measured <= 0.0 or dist <= measured + OCCLUSION_M:
            seen += 1
    return seen / len(inside)


def hero_mask_plan(
    objects: Sequence[Mapping[str, Any]],
    frames: Sequence[Mapping[str, Any]],
    hero_keyframes: Mapping[str, str],
    depths: Mapping[str, np.ndarray],
) -> list[dict[str, Any]]:
    """For each object and hero view: the detector's mask if that keyframe has one,
    otherwise a box to prompt the segmenter with, when enough of the object is in sight.

    `objects` are the objects step's output (world frame); `hero_keyframes` maps a
    hero view id to its keyframe id; `depths` are metres at each keyframe's size."""
    by_id = {f["keyframe_id"]: f for f in frames}
    plan: list[dict[str, Any]] = []
    for index, obj in enumerate(objects):
        up = int(obj["up_axis"])
        masks = {v["keyframe_id"]: v["mask"] for v in obj.get("views", [])}
        for hero_id, keyframe_id in hero_keyframes.items():
            frame, depth = by_id.get(keyframe_id), depths.get(keyframe_id)
            if frame is None or depth is None:
                continue
            share = visible_share(obj["box"], up, frame, depth)
            entry = {"object": index, "hero_view_id": hero_id, "keyframe_id": keyframe_id,
                     "visible_share": round(share, 3)}  # fmt: skip
            if keyframe_id in masks:
                plan.append({**entry, "source": "detected", "mask": masks[keyframe_id]})
                continue
            if share < MIN_VISIBLE:
                continue
            _, corners = _samples(obj["box"], up)
            uv, z = _project(corners, frame)
            uv = uv[z > 0.1]
            if len(uv) == 0:
                continue
            width, height = int(frame["width"]), int(frame["height"])
            x0, y0 = np.clip(uv.min(axis=0), 0, [width, height])
            x1, y1 = np.clip(uv.max(axis=0), 0, [width, height])
            if x1 - x0 < 4 or y1 - y0 < 4:
                continue
            box_px = [float(x0), float(y0), float(x1), float(y1)]
            plan.append({**entry, "source": "prompted", "box_px": box_px})
    return plan


def attach_hero_masks(
    twin: Mapping[str, Any], results: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Masks ({object_id, hero_view_id, mask, visible_share, source, and optionally
    outline}) onto their objects."""
    out = copy.deepcopy(_validated(twin))
    objects = {o["id"]: o for o in out["objects"]}
    for r in results:
        objects[r["object_id"]].setdefault("hero_masks", []).append(
            {
                k: r[k]
                for k in ("hero_view_id", "mask", "visible_share", "source", "outline")
                if k in r
            }
        )
    return _validated(out)
