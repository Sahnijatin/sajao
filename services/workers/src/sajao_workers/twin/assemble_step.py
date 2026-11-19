"""The assembly step: the worker's outputs become one validated SpaceTwin.

Inputs (blob digests): `capture` (Capture JSON), `frames` (frames manifest),
`objects` (objects step output), optionally `openings` (the objects step's door
and window masks), `splat` (room PLY), `phone` (phone step metadata) with
`sog_500k` and `sog_250k`. Params: `twin_id`, `version`, `created_at`. CPU
only: shell points from depth, doors and windows on the walls, surface
textures, object crops, hero views and the safe viewing region, the twin.
"""

import io
import json
from collections.abc import Callable, Mapping
from typing import Any

import numpy as np
from PIL import Image

from sajao_workers.steps import ArtifactStore, NonRetryableStepError, Step, StepContext, StepOutput
from sajao_workers.twin.assemble import AssemblyError, assemble_twin, storage_key
from sajao_workers.twin.hero import FrameView, frame_view, pick_hero_views
from sajao_workers.twin.objects import decode_depth_mm, decode_mask
from sajao_workers.twin.shell import MIN_FRAMES as OPENING_FRAMES
from sajao_workers.twin.shell import (
    TextureBuilder,
    frame_of,
    fuse_openings,
    jpeg,
    sight_opening,
    surface_rectangles,
)
from sajao_workers.twin.space import Space, fit_space

# Bump when assembly, the shell fit or the crops change.
VERSION = 7
CROP_MARGIN = 0.10  # of the mask's box, split between the two sides
CROPS_PER_OBJECT = 4

PointsForShell = Callable[[ArtifactStore, Mapping[str, Any]], np.ndarray]


def shell_points(store: ArtifactStore, manifest: Mapping[str, Any], stride: int = 8) -> np.ndarray:
    """World points (N, 3) from every frame's depth, its intrinsics scaled to the depth size."""
    chunks = []
    for frame in manifest["frames"]:
        if not frame.get("depth"):
            continue
        depth = decode_depth_mm(store.read_blob(frame["depth"]))[::stride, ::stride]
        scale = depth.shape[1] * stride / frame["width"]
        k = np.asarray(frame["intrinsics"], dtype=np.float64)
        ys, xs = np.nonzero(depth > 0.05)
        z = depth[ys, xs].astype(np.float64)
        u, v = xs * stride, ys * stride
        cam = np.stack(
            [
                (u - k[0, 2] * scale) * z / (k[0, 0] * scale),
                (v - k[1, 2] * scale) * z / (k[1, 1] * scale),
                z,
            ],
            axis=1,
        )
        pose = np.asarray(frame["c2w"], dtype=np.float64)
        chunks.append(cam @ pose[:3, :3].T + pose[:3, 3])
    return np.concatenate(chunks) if chunks else np.zeros((0, 3))


TEXTURE_IMAGE_WIDTH = 960  # keyframes are read at this width for textures
# Off until textures pass a visual check: on the ARKitScenes living room the first
# version smears furniture and streaks across the walls where the fitted wall rectangle
# misses the real wall. A wall without a texture is better than a smeared one.
ATTACH_TEXTURES = False


def _rgb(data: bytes, width: int | None = None) -> np.ndarray:
    image = Image.open(io.BytesIO(data)).convert("RGB")
    if width and image.width > width:
        image = image.resize((width, round(image.height * width / image.width)))
    return np.asarray(image)


def _shell_from_frames(
    store: ArtifactStore,
    manifest: Mapping[str, Any],
    objects: list[Any],
    openings: list[Any],
    space: Space,
    textures: bool = ATTACH_TEXTURES,
) -> dict[str, Any]:
    """Doors and windows on the walls and, if `textures`, a texture per surface, into the
    shell. Returns each surface's seen share (empty without textures)."""
    frames = {f["keyframe_id"]: f for f in manifest["frames"]}
    sightings = []
    for entry in openings:
        record = frames.get(entry["keyframe_id"])
        if record is None:
            continue
        found = sight_opening(
            entry["kind"], decode_mask(store.read_blob(entry["mask"])), frame_of(record), space
        )
        if found is not None:
            sightings.append(found)
    space.shell["openings"] = fuse_openings(
        sightings, manifest["depth_source"], 1 if manifest.get("single_view") else OPENING_FRAMES
    )

    if not textures:
        return {}
    covered: dict[str, list[str]] = {}
    for obj in objects:
        for view in obj["views"]:
            covered.setdefault(view["keyframe_id"], []).append(view["mask"])
    builders = {k: TextureBuilder(r, space) for k, r in surface_rectangles(space).items()}
    for record in manifest["frames"]:
        image = _rgb(store.read_blob(record["image"]), TEXTURE_IMAGE_WIDTH)
        depth = decode_depth_mm(store.read_blob(record["depth"])) if record.get("depth") else None
        blocked = None
        for digest in covered.get(record["keyframe_id"], []):
            mask = decode_mask(store.read_blob(digest))
            blocked = mask if blocked is None else blocked | mask
        for builder in builders.values():
            builder.add(frame_of(record), image, depth, blocked)
    coverage = {}
    for surface in space.shell["surfaces"]:
        texture, seen = builders[surface["id"]].result()
        coverage[surface["id"]] = round(seen, 2)
        if seen > 0:
            surface["texture"] = storage_key(store.put_blob(jpeg(texture)))
    return coverage


SHARPNESS_WIDTH = 480  # keyframes are read at this width to measure sharpness


def _hero_views(
    store: ArtifactStore, manifest: Mapping[str, Any]
) -> tuple[list[dict[str, float | str]], list[str]]:
    """Hero views, and the keyframes the safe region is built around (all of them).

    Nothing here depends on the room splat, so a twin without one still names
    its hero photos."""
    views: list[FrameView] = []
    for frame in manifest["frames"]:
        if not frame.get("depth"):
            continue
        grey = np.asarray(
            Image.fromarray(_rgb(store.read_blob(frame["image"]), SHARPNESS_WIDTH)).convert("L")
        )
        views.append(
            frame_view(
                frame["keyframe_id"],
                decode_depth_mm(store.read_blob(frame["depth"])),
                grey,
                frame["intrinsics"],
                frame["width"],
                frame["c2w"],
                manifest["up_axis"],
            )
        )
    return pick_hero_views(views), [f["keyframe_id"] for f in manifest["frames"]]


def _crop(image: bytes, mask: np.ndarray) -> bytes:
    rgb = Image.open(io.BytesIO(image)).convert("RGB")
    ys, xs = np.nonzero(mask)
    x0, x1, y0, y1 = int(xs.min()), int(xs.max()) + 1, int(ys.min()), int(ys.max()) + 1
    pad_x, pad_y = round(CROP_MARGIN * (x1 - x0)), round(CROP_MARGIN * (y1 - y0))
    box = (
        max(0, x0 - pad_x // 2),
        max(0, y0 - pad_y // 2),
        min(rgb.width, x1 + pad_x - pad_x // 2),
        min(rgb.height, y1 + pad_y - pad_y // 2),
    )
    buf = io.BytesIO()
    rgb.crop(box).save(buf, format="JPEG", quality=88)
    return buf.getvalue()


def _crops(
    store: ArtifactStore, manifest: Mapping[str, Any], objects: list[Any]
) -> dict[tuple[str, str], str]:
    """The largest views of each object, cropped from their keyframes."""
    images = {f["keyframe_id"]: f["image"] for f in manifest["frames"]}
    crops = {}
    for obj in objects:
        views = []
        for view in obj["views"]:
            mask = decode_mask(store.read_blob(view["mask"]))
            if view["keyframe_id"] in images and mask.any():
                views.append((int(mask.sum()), view, mask))
        views.sort(key=lambda v: -v[0])
        kept = []
        for _, view, mask in views[:CROPS_PER_OBJECT]:
            image = store.read_blob(images[view["keyframe_id"]])
            crops[(view["keyframe_id"], view["mask"])] = store.put_blob(_crop(image, mask))
            kept.append(view)
        obj["views"] = kept
    return crops


def _optional(context: StepContext, name: str, default: Any) -> Any:
    return json.loads(context.read(name)) if name in context.inputs else default


def assemble_step(points_for_shell: PointsForShell = shell_points) -> Step:
    async def run(context: StepContext) -> StepOutput:
        capture = json.loads(context.read("capture"))
        manifest = json.loads(context.read("frames"))
        objects = json.loads(context.read("objects"))
        # A single photo has no splat, so no phone variants.
        phone = _optional(context, "phone", {"variants": {}})
        points = points_for_shell(context.store, manifest)
        if len(points) < 1000:
            raise NonRetryableStepError("too little depth to fit the room shell")
        single = bool(manifest.get("single_view"))
        space = fit_space(
            points,
            depth_source=manifest["depth_source"],
            unseen_open=single,
            stood_at=np.asarray(manifest["frames"][0]["c2w"])[:3, 3] if single else None,
        )
        openings = json.loads(context.read("openings")) if "openings" in context.inputs else []
        coverage = _shell_from_frames(context.store, manifest, objects, openings, space)
        crops = _crops(context.store, manifest, objects)
        hero_views, anchor_ids = _hero_views(context.store, manifest)
        phone_splats = [
            {
                "budget": int(tag.rstrip("k")) * 1000,
                "sog": context.inputs[f"sog_{tag}"],
                **variant,
            }
            for tag, variant in phone["variants"].items()
            if f"sog_{tag}" in context.inputs
        ]
        try:
            twin = assemble_twin(
                twin_id=context.params["twin_id"],
                version=int(context.params["version"]),
                created_at=context.params["created_at"],
                capture=capture,
                manifest=manifest,
                space=space,
                objects=objects,
                crops=crops,
                splat=context.inputs.get("splat"),
                phone_splats=phone_splats,
                hero_views=hero_views,
                anchor_ids=anchor_ids,
                built_ins=_optional(context, "built_ins", []),
                inventory=_optional(context, "inventory", None),
                scale=_optional(context, "scale", None),
            )
        except AssemblyError as error:
            raise NonRetryableStepError(str(error)) from error
        return StepOutput(
            files={"twin": json.dumps(twin, sort_keys=True).encode()},
            meta={
                "objects": len(twin["objects"]),
                "space_type": twin["space_type"],
                "extent": twin["extent"],
                "walls_m": [w["length"]["value_m"] for w in twin["shell"]["walls"]],
                "ceiling_m": twin["shell"]["ceiling_height"]["value_m"],
                "north_deg": (twin.get("direction") or {}).get("north_deg"),
                "openings": [o["kind"] for o in twin["shell"]["openings"]],
                "built_ins": len(twin["shell"].get("built_ins", [])),
                "unplaced": len(twin.get("inventory", {}).get("unplaced", [])),
                "texture_coverage": coverage,
                "hero_views": [v["keyframe_id"] for v in hero_views],
                "confidence": twin["confidence"]["level"],
            },
        )

    return Step("twin_assemble", VERSION, run)
