"""Assembling the SpaceTwin from the worker's step outputs.

Everything the twin says comes from measurement and code: boxes from depth,
the shell from depth, the scale from AR, the direction from the compass. No
model sets a dimension. The result is checked against the generated SpaceTwin
model before anything stores it.

Conventions: positions are in the space frame (metres, z up from the floor).
Keyframe poses are camera-to-space with OpenCV camera axes (+X right, +Y down,
+Z forward). Storage keys point at blobs in the artifact store.
"""

import math
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from sajao_schemas import to_json_dict
from sajao_schemas.generated.v1 import SpaceTwin
from sajao_workers.twin.confidence import confidence_level
from sajao_workers.twin.hero import ORBIT_YAW_DEG, SAFE_RADIUS_M
from sajao_workers.twin.space import Space

SCHEMA_VERSION = "1.0"
TIERS = {500_000: "capable", 250_000: "budget"}
MAX_VIEWS = 4
LIVING = {"sofa", "armchair", "television"}


class AssemblyError(Exception):
    """The outputs cannot make a valid twin (missing compass, schema violation)."""


def storage_key(digest: str) -> str:
    return f"artifacts/blobs/{digest[:2]}/{digest}"


def space_type_from(categories: Sequence[str]) -> str:
    """A first guess from what was found; the user can change it.

    Beds vote for a bedroom, sofas, armchairs and televisions for a living
    room; a bed wins ties, so one stray detection cannot outvote a room.
    """
    beds = sum(c == "bed" for c in categories)
    living = sum(c in LIVING for c in categories)
    if beds and beds >= living:
        return "bedroom"
    if living:
        return "living_room"
    return "other"


def _quaternion(r: np.ndarray) -> list[float]:
    """Unit quaternion (x, y, z, w) of a rotation matrix."""
    trace = r[0, 0] + r[1, 1] + r[2, 2]
    if trace > 0:
        s = 2.0 * math.sqrt(trace + 1.0)
        q = [(r[2, 1] - r[1, 2]) / s, (r[0, 2] - r[2, 0]) / s, (r[1, 0] - r[0, 1]) / s, s / 4]
    else:
        i = int(np.argmax([r[0, 0], r[1, 1], r[2, 2]]))
        j, k = (i + 1) % 3, (i + 2) % 3
        s = 2.0 * math.sqrt(1.0 + r[i, i] - r[j, j] - r[k, k])
        q = [0.0, 0.0, 0.0, (r[k, j] - r[j, k]) / s]
        q[i] = s / 4
        q[j] = (r[j, i] + r[i, j]) / s
        q[k] = (r[k, i] + r[i, k]) / s
    norm = math.sqrt(sum(v * v for v in q))
    return [round(v / norm, 9) for v in q]


def _point(xyz: tuple[float, float, float]) -> dict[str, float]:
    return {"x_m": round(xyz[0], 3), "y_m": round(xyz[1], 3), "z_m": round(xyz[2], 3)}


def _keyframes(capture: Mapping[str, Any], manifest: Mapping[str, Any], space: Space) -> list[Any]:
    timing = {k["id"]: k for k in capture["package"]["keyframes"]}
    out = []
    for frame in manifest["frames"]:
        c2w = np.asarray(frame["c2w"], dtype=np.float64)
        k = frame["intrinsics"]
        meta = timing.get(frame["keyframe_id"], {})
        keyframe: dict[str, Any] = {
            "id": frame["keyframe_id"],
            "image": storage_key(frame["image"]),
            "captured_at_ms": int(meta.get("captured_at_ms", 0)),
            "pose": {
                "position": _point(space.point(c2w[:3, 3])),
                "rotation": _quaternion(space.rotation @ c2w[:3, :3]),
            },
            "intrinsics": {
                "fx": k[0][0],
                "fy": k[1][1],
                "cx": k[0][2],
                "cy": k[1][2],
                "width_px": frame["width"],
                "height_px": frame["height"],
            },
        }
        if "sharpness" in meta:
            keyframe["sharpness"] = meta["sharpness"]
        out.append(keyframe)
    return out


def _viewing(
    keyframes: Sequence[Mapping[str, Any]],
    hero_views: Sequence[Mapping[str, Any]],
    anchor_ids: Sequence[str],
) -> dict[str, Any]:
    """Hero views and the safe region around the keyframe positions."""
    positions = {k["id"]: k["pose"]["position"] for k in keyframes}
    return {
        "hero_views": [
            {
                "id": f"h{index}",
                "keyframe_id": view["keyframe_id"],
                "coverage": view["coverage"],
                "sharpness": view["sharpness"],
                "orbit": {"max_offset_m": SAFE_RADIUS_M, "max_yaw_deg": ORBIT_YAW_DEG},
            }
            for index, view in enumerate(hero_views, start=1)
        ],
        "safe_region": {
            "anchors": [positions[i] for i in anchor_ids if i in positions],
            "radius_m": SAFE_RADIUS_M,
        },
    }


def _box(box: Mapping[str, Any], space: Space) -> dict[str, Any]:
    return {
        "center": _point(space.point(box["center"])),
        "yaw_deg": round(space.yaw_deg(box["yaw_deg"]), 2),
        "width": box["length"],  # the longer horizontal side
        "depth": box["width"],
        "height": box["height"],
    }


def _built_ins(built_ins: Sequence[Mapping[str, Any]], space: Space) -> list[dict[str, Any]]:
    return [
        {
            "id": f"b{index}",
            "category": b["category"],
            "label": b["label"],
            "box": _box(b["box"], space),
            "detection": {"source": "server_segmentation", "confidence": b["confidence"]},
        }
        for index, b in enumerate(built_ins, start=1)
    ]


def _objects(
    objects: Sequence[Mapping[str, Any]],
    crops: Mapping[tuple[str, str], str],
    space: Space,
) -> list[Any]:
    out = []
    for index, obj in enumerate(objects, start=1):
        views = [
            {
                "keyframe_id": v["keyframe_id"],
                "mask": storage_key(v["mask"]),
                "crop": storage_key(crops[(v["keyframe_id"], v["mask"])]),
            }
            for v in obj["views"]
            if (v["keyframe_id"], v["mask"]) in crops
        ][:MAX_VIEWS]
        twin_object = {
            "id": f"o{index}",
            "category": obj["category"],
            "label": obj["label"],
            "box": _box(obj["box"], space),
            "detection": {"source": "server_segmentation", "confidence": obj["confidence"]},
            "views": views,
            "catalog_matches": [],
            "state": "keep",
        }
        if "object_type" in obj:
            twin_object["object_type"] = obj["object_type"]
        out.append(twin_object)
    return out


def _photo_heading(
    capture: Mapping[str, Any], manifest: Mapping[str, Any]
) -> dict[str, Any] | None:
    """A single photo's own compass heading, as a compass reading. Its camera looks
    along the world's -z, the direction a capture's compass bearing describes."""
    if not manifest.get("single_view"):
        return None
    headings = [
        m["compass_heading_deg"]
        for m in capture.get("media", [])
        if m.get("kind") == "photo" and "compass_heading_deg" in m
    ]
    return {"mean_heading_deg": headings[0]} if len(headings) == 1 else None


def _widen(node: Any, fraction: float) -> None:
    """Every Dimension under `node` gets an error band of at least `fraction` of it."""
    if isinstance(node, dict):
        if {"value_m", "error_band_m", "source"} <= node.keys():
            band = max(float(node["error_band_m"]), fraction * float(node["value_m"]))
            node["error_band_m"] = round(band, 3)
            return
        for value in node.values():
            _widen(value, fraction)
    elif isinstance(node, list):
        for value in node:
            _widen(value, fraction)


def assemble_twin(
    *,
    twin_id: str,
    version: int,
    created_at: str,
    capture: Mapping[str, Any],
    manifest: Mapping[str, Any],
    space: Space,
    objects: Sequence[Mapping[str, Any]],
    crops: Mapping[tuple[str, str], str],
    splat: str | None,
    phone_splats: Sequence[Mapping[str, Any]],
    built_ins: Sequence[Mapping[str, Any]] = (),
    inventory: Mapping[str, Any] | None = None,
    hero_views: Sequence[Mapping[str, Any]] = (),
    anchor_ids: Sequence[str] = (),
    scale: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """The SpaceTwin as JSON-ready data, validated against the schema.

    `built_ins` (from the objects step) join the shell; `inventory` records what
    the vision models listed and every item that could not be placed.
    `hero_views` are hero.pick_hero_views' picks and `anchor_ids` the keyframes
    the safe region is built around; without hero views the twin has no viewing
    section and nothing may show it from a free camera. `scale` is the single-photo
    scale check: its evidence becomes the twin's `scale`, and no shell length is
    claimed tighter than its band."""
    compass = capture.get("compass") or _photo_heading(capture, manifest)
    if not compass:
        raise AssemblyError("the capture has no compass reading, so north cannot be set")
    twin: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "id": twin_id,
        "capture_id": capture["id"],
        "version": version,
        "created_at": created_at,
        "space_type": space_type_from([o["category"] for o in objects]),
        "space_type_source": "detected",
        "extent": space.extent,
        "extent_source": "detected",
        "shell": {
            **space.shell,
            **({"built_ins": _built_ins(built_ins, space)} if built_ins else {}),
        },
        "objects": _objects(objects, crops, space),
        "keyframes": _keyframes(capture, manifest, space),
        # AR scale with error bands; a tape value is asked only when a fit decision needs it.
        "scale": {
            "anchors": [{"kind": "geometry_model", "implied_scale": 1.0}],
            "anchors_agree": True,
            "needs_tape_value": False,
        },
        "direction": {
            "north_deg": round(space.north_deg(float(compass["mean_heading_deg"])), 2),
            "confidence": "approximate",
            "sources": ["compass"],
        },
        # The shell comes from depth: LiDAR measures it, a depth model only estimates it.
        "confidence": dict(
            confidence_level("lidar" if manifest.get("depth_source") == "lidar" else "depth_model")
        ),
    }
    if scale is not None:
        twin["scale"] = dict(scale["evidence"])
        _widen(twin["shell"], float(scale["band_fraction"]))
    if hero_views:
        twin["viewing"] = _viewing(twin["keyframes"], hero_views, anchor_ids)
    if inventory is not None:
        twin["inventory"] = dict(inventory)
    if splat:
        twin["splat"] = {"key": storage_key(splat), "format": "ply"}
    if phone_splats:
        twin["phone_splats"] = [
            {
                "key": storage_key(p["sog"]),
                "format": "sog",
                "tier": TIERS[p["budget"]],
                "gaussians": p["gaussians"],
                "bytes": p["bytes"],
            }
            for p in phone_splats
        ]
    try:
        model = SpaceTwin.model_validate(twin)
    except ValueError as error:
        raise AssemblyError(f"the twin does not validate: {error}") from error
    validated: dict[str, Any] = to_json_dict(model)
    return validated
