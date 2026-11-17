"""The golden-room accuracy report: a twin against the tape measurements of the room."""

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from sajao_workers.golden import (
    SheetError,
    accuracy_report,
    ground_truth_sizes,
    inventory_recall,
    markdown,
    read_sheet,
)

FIXTURE = Path(__file__).parents[3] / "packages/schemas/fixtures/v1/valid/space-twin.json"


def twin() -> dict[str, Any]:
    doc: dict[str, Any] = json.loads(FIXTURE.read_text())
    return doc  # a 4.2 x 3.4 m room, ceiling 2.9 m, a door on w4, a sofa and an almirah


def sheet(**change: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "room": "Test bedroom 1",
        "unit": "cm",
        # Clockwise from the door: the door is on the twin's w4, so W1 is the twin's w4.
        "walls": {"W1": 342, "W2": 418, "W3": 338, "W4": 425},
        "ceiling": [288, 292],
        "doors": [{"wall": "W1", "width": 92, "height": 206, "offset": 28}],
        "windows": [],
        "furniture": [{"name": "sofa", "width": 205, "depth": 88, "height": 84}],
    }
    base.update(change)
    return base


def test_a_sheet_is_read_in_metres() -> None:
    read = read_sheet(sheet())
    assert read.walls == [3.42, 4.18, 3.38, 4.25]
    assert read.ceiling == [2.88, 2.92]
    assert read.doors[0]["width"] == pytest.approx(0.92)


@pytest.mark.parametrize(
    "change",
    [{"unit": "inch"}, {"walls": {}}, {"ceiling": []}, {"walls": {"W1": -3, "W2": 400}}],
)
def test_a_bad_sheet_is_refused(change: dict[str, Any]) -> None:
    with pytest.raises(SheetError):
        read_sheet(sheet(**change))


def test_walls_are_paired_in_the_best_turn_and_direction() -> None:
    report = accuracy_report(twin(), read_sheet(sheet()))

    pairs = {w["tape"]: w["twin"] for w in report["walls"]}
    assert pairs == {"W1": "w4", "W2": "w1", "W3": "w2", "W4": "w3"}
    w2 = next(w for w in report["walls"] if w["tape"] == "W2")
    assert w2["error_m"] == pytest.approx(0.02)  # twin minus tape
    assert w2["within_band"] is False  # w1 claims 1 cm: a tape value the user confirmed


def test_ceiling_doors_and_furniture_are_scored() -> None:
    report = accuracy_report(twin(), read_sheet(sheet()))

    assert report["ceiling"]["tape_m"] == pytest.approx(2.90)
    assert report["ceiling"]["error_m"] == pytest.approx(0.0)
    door = report["openings"][0]
    assert door["found"] and door["twin"] == "d1"
    assert door["width_error_m"] == pytest.approx(-0.02)
    sofa = report["furniture"][0]
    assert sofa["twin"] == "sofa-1"
    assert set(sofa["errors_m"]) == {"width", "depth", "height"}


def test_a_window_the_twin_missed_is_reported_missing() -> None:
    windows = [{"wall": "W2", "width": 150, "height": 120, "sill": 90, "offset": 40},
               {"wall": "W4", "width": 100, "height": 120, "sill": 90, "offset": 10}]  # fmt: skip

    report = accuracy_report(twin(), read_sheet(sheet(windows=windows)))

    found = [o for o in report["openings"] if o["kind"] == "window"]
    assert sum(o["found"] for o in found) == 1
    assert report["summary"]["openings_found"] == "2 of 3"


def test_a_room_with_more_walls_than_the_twin_is_flagged_not_forced() -> None:
    walls = {"W1": 342, "W2": 418, "W3": 120, "W4": 218, "W5": 425}

    report = accuracy_report(twin(), read_sheet(sheet(walls=walls)))

    assert report["walls"] == []
    assert "5 walls" in report["notes"][0]


def test_the_summary_gives_the_golden_set_dimension_error() -> None:
    report = accuracy_report(twin(), read_sheet(sheet()))

    summary = report["summary"]
    assert 0 < summary["dimension_error_pct"] < 2.0
    assert summary["walls_within_band"] == "3 of 4"
    text = markdown(report)
    assert "Test bedroom 1" in text and "| W2 | w1 |" in text


def test_recall_against_the_listed_inventory_is_per_type() -> None:
    doc = twin()
    doc["objects"][0]["object_type"] = "furniture"  # sofa-1
    doc["objects"][1]["object_type"] = "furniture"
    doc["inventory"] = {
        "listed_by": ["gemini-3-flash-preview"],
        "items_listed": 5,
        "unplaced": [
            {"name": "wall clock", "type": "wall_item", "count": 1, "listed_by": ["m"],
             "tried": ["owlv2: wall clock"], "reason": "not_seen_in_enough_frames"},
            {"name": "geyser", "type": "fixture", "count": 1, "listed_by": ["m"],
             "tried": ["owlv2: geyser"], "reason": "not_detected"},
        ],
    }  # fmt: skip

    section = inventory_recall(doc)

    assert section is not None
    assert section["listed"] == 5 and section["placed"] == 3  # the radiator is a built-in
    assert section["by_type"]["furniture"] == {"listed": 2, "placed": 2, "recall": 1.0}
    assert section["by_type"]["built_in"] == {"listed": 1, "placed": 1, "recall": 1.0}
    assert section["by_type"]["fixture"] == {"listed": 1, "placed": 0, "recall": 0.0}
    assert [u["name"] for u in section["unplaced"]] == ["wall clock", "geyser"]


def test_a_twin_without_an_inventory_has_no_recall_section() -> None:
    doc = twin()
    del doc["inventory"]
    assert inventory_recall(doc) is None


def test_box_sizes_are_scored_against_ground_truth_boxes() -> None:
    doc = twin()
    sofa = doc["objects"][0]
    centre = [sofa["box"]["center"][a] for a in ("x_m", "y_m", "z_m")]
    w, d = sofa["box"]["width"]["value_m"], sofa["box"]["depth"]["value_m"]
    truth = [
        # The sofa, 10 cm off and 10% longer than the twin says; the same object seen in AR world
        # coordinates that the identity transform maps onto the twin's space.
        {"label": "sofa", "center": [centre[0] + 0.1, centre[1], centre[2]],
         "size_m": [w * 1.1, d, sofa["box"]["height"]["value_m"]]},
        {"label": "bathtub", "center": [0.5, 0.5, 0.3], "size_m": [1.6, 0.7, 0.5]},
    ]  # fmt: skip

    report = ground_truth_sizes(doc, truth, np.eye(4))

    (matched, missed) = report["boxes"]
    assert matched["twin"] == "sofa-1" and missed["twin"] is None
    assert matched["error_pct"]["width"] == pytest.approx(-9.1, abs=0.2)
    assert report["summary"]["matched"] == "1 of 2"


def test_the_report_carries_both_sections_when_there_is_ground_truth() -> None:
    truth = [{"label": "sofa", "center": [2.1, 0.6, 0.42], "size_m": [2.0, 0.9, 0.85]}]

    report = accuracy_report(twin(), read_sheet(sheet()), truth=truth, to_space=np.eye(4))

    assert report["inventory"]["listed"] == 14
    assert report["ground_truth"]["summary"]["matched"] == "1 of 1"
    text = markdown(report)
    assert "## Objects against the listed inventory" in text
    assert "## Box sizes against ground truth" in text
    assert "| sofa | sofa-1 |" in text


def test_without_ground_truth_the_report_says_so() -> None:
    report = accuracy_report(twin(), read_sheet(sheet()))

    assert report["ground_truth"] is None
    assert "## Box sizes against ground truth" not in markdown(report)
