"""Room understanding for design: footprints, keep or replace, free floor, hero masks."""

import copy
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from sajao_schemas.generated.v1 import SpaceTwin
from sajao_workers.twin.understanding import (
    attach_hero_masks,
    footprint,
    free_floor,
    hero_mask_plan,
    understand_room,
)

FIXTURE = Path(__file__).parents[3] / "packages/schemas/fixtures/v1/valid/space-twin.json"


def twin() -> dict[str, Any]:
    doc: dict[str, Any] = json.loads(FIXTURE.read_text())
    for obj in [*doc["objects"], *doc["shell"].get("built_ins", [])]:
        for key in ("footprint", "redesign", "hero_masks"):
            obj.pop(key, None)
    doc.pop("free_floor", None)
    return doc


def dim(v: float, band: float = 0.05) -> dict[str, Any]:
    return {"value_m": v, "source": "estimated", "error_band_m": band}


def box(
    x: float, y: float, z: float, w: float, d: float, h: float, yaw: float = 0.0
) -> dict[str, Any]:
    return {"center": {"x_m": x, "y_m": y, "z_m": z}, "yaw_deg": yaw,
            "width": dim(w), "depth": dim(d), "height": dim(h)}  # fmt: skip


# Footprints and keep or replace -------------------------------------------------


def test_a_sofa_footprint_is_its_box_from_above_and_it_stands_on_the_floor() -> None:
    fp = footprint(box(2.0, 1.0, 0.42, 2.0, 0.9, 0.84, yaw=90.0))

    xs = sorted(round(p["x_m"], 3) for p in fp["polygon"])
    ys = sorted(round(p["y_m"], 3) for p in fp["polygon"])
    assert xs == [1.55, 1.55, 2.45, 2.45] and ys == [0.0, 0.0, 2.0, 2.0]
    assert fp["width"]["value_m"] == 2.0 and fp["depth"]["error_band_m"] == 0.05
    assert fp["on_floor"] is True


def test_a_wall_clock_does_not_take_up_floor() -> None:
    assert footprint(box(1.0, 0.05, 1.8, 0.3, 0.05, 0.3))["on_floor"] is False


def test_fixtures_are_kept_and_furniture_may_be_replaced_and_a_choice_by_the_person_wins() -> None:
    doc = twin()
    doc["objects"][0]["object_type"] = "furniture"
    doc["objects"][1]["object_type"] = "fixture"
    chosen = copy.deepcopy(doc)
    chosen["objects"][0]["redesign"] = {"state": "keep", "source": "user"}

    out = understand_room(doc)
    kept = understand_room(chosen)

    SpaceTwin.model_validate(out)
    assert [o["redesign"] for o in out["objects"]] == [
        {"state": "replace", "source": "rule"},
        {"state": "keep", "source": "rule"},
    ]
    assert kept["objects"][0]["redesign"] == {"state": "keep", "source": "user"}
    assert all("footprint" in o for o in [*out["objects"], *out["shell"]["built_ins"]])
    assert out is not doc and "free_floor" not in doc  # the input is not changed


# Free floor -------------------------------------------------------------------


def test_free_floor_is_the_floor_less_what_is_kept_on_it() -> None:
    doc = twin()
    floor = (
        sum(
            p["x_m"] * q["y_m"] - q["x_m"] * p["y_m"]
            for p, q in zip(
                doc["shell"]["floor_polygon"],
                [*doc["shell"]["floor_polygon"][1:], doc["shell"]["floor_polygon"][0]],
                strict=True,
            )
        )
        / 2
    )
    doc["objects"][0]["object_type"] = "furniture"  # replaced: its floor counts as free
    doc["objects"][1]["object_type"] = "fixture"  # kept

    out = understand_room(doc)
    ff = out["free_floor"]

    almirah = out["objects"][1]["footprint"]
    radiator = out["shell"]["built_ins"][0]["footprint"]
    taken = sum(f["width"]["value_m"] * f["depth"]["value_m"] for f in (almirah, radiator))
    assert ff["floor_area_m2"] == pytest.approx(abs(floor), rel=0.01)
    assert ff["area_m2"] == pytest.approx(abs(floor) - taken, abs=0.05)
    assert sorted(ff["kept_ids"]) == ["almirah-1", "b1"]
    assert ff["error_band_m2"] > 0


def test_free_floor_never_counts_floor_outside_the_room() -> None:
    doc = twin()
    doc["objects"][1]["object_type"] = "fixture"
    doc["objects"][1]["box"] = box(-5.0, -5.0, 0.5, 1.0, 1.0, 1.0)  # outside the floor polygon

    assert free_floor(understand_room(doc))["area_m2"] == pytest.approx(
        understand_room(doc)["free_floor"]["floor_area_m2"]
        - sum(
            f["width"]["value_m"] * f["depth"]["value_m"]
            for f in [understand_room(doc)["shell"]["built_ins"][0]["footprint"]]
        ),
        abs=0.05,
    )


# Hero masks -------------------------------------------------------------------

W, H, F = 640, 480, 400.0
K = [[F, 0.0, W / 2], [0.0, F, H / 2], [0.0, 0.0, 1.0]]


def camera(x: float, yaw_deg: float = 0.0) -> list[list[float]]:
    """A level OpenCV camera at (x, 0, 1.4) in a z-up world, looking along +y turned by yaw."""
    yaw = math.radians(yaw_deg)
    forward = np.array([-math.sin(yaw), math.cos(yaw), 0.0])
    down = np.array([0.0, 0.0, -1.0])
    right = np.cross(down, forward)
    c2w = np.eye(4)
    c2w[:3, :3] = np.column_stack([right, down, forward])
    c2w[:3, 3] = [x, 0.0, 1.4]
    return c2w.tolist()


def world_box(x: float, y: float, w: float = 1.0) -> dict[str, Any]:
    return {"center": [x, y, 0.4], "yaw_deg": 0.0, "length": dim(w), "width": dim(w),
            "height": dim(0.8)}  # fmt: skip


def frames() -> list[dict[str, Any]]:
    return [
        {"keyframe_id": "k1", "width": W, "height": H, "intrinsics": K, "c2w": camera(0.0)},
        {"keyframe_id": "k2", "width": W, "height": H, "intrinsics": K, "c2w": camera(0.0, 180.0)},
    ]


def test_a_hero_view_reuses_the_detectors_mask_or_asks_for_one_from_the_box() -> None:
    objects = [
        {"up_axis": 2, "box": world_box(0.0, 3.0), "views": [{"keyframe_id": "k1", "mask": "m1"}]},
        {"up_axis": 2, "box": world_box(0.6, 3.5), "views": []},  # seen, but not detected in k1
    ]
    depths = {"k1": np.full((H, W), 6.0), "k2": np.full((H, W), 6.0)}

    plan = hero_mask_plan(objects, frames(), {"h1": "k1", "h2": "k2"}, depths)

    detected = [p for p in plan if p["source"] == "detected"]
    prompted = [p for p in plan if p["source"] == "prompted"]
    assert [(p["object"], p["hero_view_id"], p["mask"]) for p in detected] == [(0, "h1", "m1")]
    assert [(p["object"], p["hero_view_id"]) for p in prompted] == [(1, "h1")]
    x0, y0, x1, y1 = prompted[0]["box_px"]
    assert 0 <= x0 < x1 <= W and 0 <= y0 < y1 <= H
    assert all(p["visible_share"] > 0.5 for p in plan)  # nothing is planned for k2: behind it


def test_something_hidden_behind_a_nearer_wall_gets_no_mask() -> None:
    objects = [{"up_axis": 2, "box": world_box(0.0, 3.0), "views": []}]
    wall = {"k1": np.full((H, W), 1.5), "k2": np.full((H, W), 6.0)}  # a surface 1.5 m away

    assert hero_mask_plan(objects, frames(), {"h1": "k1"}, wall) == []


def test_masks_are_attached_to_their_objects_by_hero_view() -> None:
    doc = understand_room(twin())
    results = [
        {"object_id": "sofa-1", "hero_view_id": "h1", "mask": "masks/a.png",
         "visible_share": 0.8, "source": "prompted"},
    ]  # fmt: skip

    out = attach_hero_masks(doc, results)

    SpaceTwin.model_validate(out)
    assert out["objects"][0]["hero_masks"] == [
        {"hero_view_id": "h1", "mask": "masks/a.png", "visible_share": 0.8, "source": "prompted"}
    ]
    assert "hero_masks" not in out["objects"][1]


def test_furniture_stands_on_the_floor_even_when_its_lower_part_was_hidden() -> None:
    armchair = box(1.0, 1.0, 0.85, 0.7, 0.5, 0.5)  # only the back was seen: bottom 0.6 m up
    assert footprint(armchair, "furniture", "armchair")["on_floor"] is True
    assert footprint(armchair, "furniture", "wall shelf")["on_floor"] is False


def test_wall_items_never_take_floor_and_a_tv_on_a_stand_does_not_either() -> None:
    leaning = box(1.0, 0.1, 0.5, 0.9, 0.1, 1.0)  # a painting leaning on the floor
    tv = box(2.0, 0.3, 0.66, 1.0, 0.2, 0.6)  # bottom 0.36 m up
    assert footprint(leaning, "wall_item", "painting")["on_floor"] is False
    assert footprint(tv, "fixture", "tv")["on_floor"] is False
    assert footprint(box(3.0, 0.1, 0.36, 1.0, 0.2, 0.7), "fixture", "radiator")["on_floor"] is True
