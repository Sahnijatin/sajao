"""Assembling the SpaceTwin from the worker's step outputs; it must validate."""

import json
import math
from collections.abc import Callable
from typing import Any

import numpy as np
import pytest

from sajao_schemas.generated.v1 import SpaceTwin
from sajao_workers.twin.assemble import (
    assemble_twin,
    space_type_from,
    storage_key,
)
from sajao_workers.twin.space import fit_space

Room = Callable[..., np.ndarray]  # the room fixture from conftest.py

D = "ab" + "0" * 62  # a blob digest


def capture() -> dict[str, Any]:
    return {
        "id": "7f9c2b1e-4c1d-4f3a-9a77-1e2d3c4b5a60",
        "compass": {"mean_heading_deg": 91.0, "sample_count": 24},
        "package": {
            "ar": {"tracking": "arkit", "lidar": True, "depth": True},
            "keyframes": [
                {
                    "id": f"k{i}",
                    "image": f"c/k{i}.jpg",
                    "captured_at_ms": 500 * i,
                    "sharpness": 300.0,
                }
                for i in range(1, 4)
            ],
            "detections": [],
            "sensor_log": "c/sensors.jsonl",
        },
    }


def manifest() -> dict[str, Any]:
    eye = [[1.0, 0, 0, 0.5], [0, -1.0, 0, 1.4], [0, 0, -1.0, 1.0], [0, 0, 0, 1.0]]
    k = [[500.0, 0.0, 320.0], [0.0, 500.0, 240.0], [0.0, 0.0, 1.0]]
    frames = [
        {
            "keyframe_id": f"k{i}",
            "image": D,
            "width": 640,
            "height": 480,
            "intrinsics": k,
            "c2w": eye,
            "depth": D,
        }
        for i in range(1, 4)
    ]
    return {"up_axis": 1, "depth_source": "lidar", "frames": frames}


def objects() -> list[dict[str, Any]]:
    dim = {"value_m": 1.9, "source": "estimated", "error_band_m": 0.475}
    return [
        {
            "category": "sofa",
            "label": "Sofa",
            "confidence": 0.81,
            "frames": 12,
            "up_axis": 1,
            "box": {
                "center": [2.0, 0.4, 1.0],
                "yaw_deg": 10.0,
                "length": dim,
                "width": dim,
                "height": dim,
            },
            "views": [{"keyframe_id": "k1", "mask": D}, {"keyframe_id": "k2", "mask": D}],
        }
    ]


def build(room: Room, **changes: Any) -> dict[str, Any]:
    args: dict[str, Any] = {
        "twin_id": "0b7e3a4c-2f1d-4e5a-8b6c-7d8e9f0a1b2c",
        "version": 1,
        "created_at": "2026-11-16T10:00:00Z",
        "capture": capture(),
        "manifest": manifest(),
        "space": fit_space(room(), depth_source="lidar"),
        "objects": objects(),
        "crops": {("k1", D): D, ("k2", D): D},
        "splat": D,
        "phone_splats": [
            {"budget": 500_000, "gaussians": 500_000, "sog": D, "bytes": 5_971_379},
            {"budget": 250_000, "gaussians": 250_000, "sog": D, "bytes": 3_021_338},
        ],
    }
    return assemble_twin(**{**args, **changes})


def test_the_assembled_twin_validates_against_the_schema(room: Room) -> None:
    twin = build(room)

    SpaceTwin.model_validate(twin)
    assert json.loads(json.dumps(twin)) == twin  # plain JSON


def test_the_twin_says_how_far_its_measurements_can_be_trusted(room: Room) -> None:
    assert build(room)["confidence"] == {"level": "ar_measured", "basis": "lidar", "tape_values": 0}
    estimated = build(room, manifest={**manifest(), "depth_source": "image"})
    assert estimated["confidence"]["level"] == "estimated"
    assert estimated["confidence"]["basis"] == "depth_model"


def test_scale_never_asks_for_tape_up_front(room: Room) -> None:
    scale = build(room)["scale"]
    assert scale["needs_tape_value"] is False
    assert scale["anchors"] == [{"kind": "geometry_model", "implied_scale": 1.0}]


def test_objects_are_in_the_space_frame_with_their_bands(room: Room) -> None:
    twin = build(room)
    sofa = twin["objects"][0]
    space = fit_space(room(), depth_source="lidar")
    x, y, z = space.point([2.0, 0.4, 1.0])

    assert sofa["box"]["center"] == {"x_m": round(x, 3), "y_m": round(y, 3), "z_m": round(z, 3)}
    assert sofa["box"]["width"]["error_band_m"] == 0.475
    assert sofa["detection"] == {"source": "server_segmentation", "confidence": 0.81}
    assert sofa["state"] == "keep"
    assert sofa["views"][0] == {"keyframe_id": "k1", "mask": storage_key(D), "crop": storage_key(D)}


def test_north_comes_from_the_compass_turned_into_the_space_frame(
    room: Room,
) -> None:
    twin = build(room)
    space = fit_space(room(), depth_source="lidar")

    assert twin["direction"] == {
        "north_deg": round(space.north_deg(91.0), 2),
        "confidence": "approximate",
        "sources": ["compass"],
    }


def test_a_capture_without_a_compass_has_no_direction(room: Room) -> None:
    no_compass = capture()
    del no_compass["compass"]
    twin = build(room, capture=no_compass)
    assert "direction" not in twin


def test_phone_splats_are_listed_by_tier(room: Room) -> None:
    tiers = {p["tier"]: p for p in build(room)["phone_splats"]}
    assert tiers["capable"]["gaussians"] == 500_000 and tiers["budget"]["bytes"] == 3_021_338
    assert {p["format"] for p in tiers.values()} == {"sog"}


def test_keyframe_poses_are_unit_quaternions_in_the_space_frame(
    room: Room,
) -> None:
    for keyframe in build(room)["keyframes"]:
        q = keyframe["pose"]["rotation"]
        assert math.isclose(math.sqrt(sum(v * v for v in q)), 1.0, abs_tol=1e-6)


@pytest.mark.parametrize(
    ("categories", "expected"),
    [
        (["bed", "lamp"], "bedroom"),
        (["sofa", "table"], "living_room"),
        (["chair"], "other"),
        # A stray bed detection does not outvote three sofas.
        (["sofa", "sofa", "sofa", "bed", "television"], "living_room"),
        (["bed", "armchair"], "bedroom"),
    ],
)
def test_space_type_comes_from_what_was_found(categories: list[str], expected: str) -> None:
    assert space_type_from(categories) == expected


def test_types_built_ins_and_the_inventory_reach_the_twin(room: Room) -> None:
    sofa = {**objects()[0], "object_type": "furniture"}
    chimney = {**objects()[0], "category": "chimney", "label": "Chimney"}
    inventory = {
        "listed_by": ["gemini-3-flash-preview", "claude-opus-5-5"],
        "items_listed": 3,
        "unplaced": [
            {
                "name": "wall clock",
                "type": "wall_item",
                "count": 1,
                "listed_by": ["claude-opus-5-5"],
                "tried": ["owlv2: wall clock", "owlv2: clock (min score 0.1)"],
                "reason": "not_seen_in_enough_frames",
            }
        ],
    }

    twin = build(room, objects=[sofa], built_ins=[chimney], inventory=inventory)

    SpaceTwin.model_validate(twin)
    assert twin["objects"][0]["object_type"] == "furniture"
    (built_in,) = twin["shell"]["built_ins"]
    assert built_in["id"] == "b1" and built_in["category"] == "chimney"
    assert built_in["box"]["width"]["value_m"] == 1.9
    assert twin["inventory"] == inventory
