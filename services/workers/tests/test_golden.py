"""The golden-room accuracy report: a twin against the tape measurements of the room."""

import json
from pathlib import Path
from typing import Any

import pytest

from sajao_workers.golden import SheetError, accuracy_report, markdown, read_sheet

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


def test_render_quality_is_reported_near_and_far_from_the_capture_path() -> None:
    heldout = {
        "near": {"views": 7, "psnr": 26.41, "ssim": 0.871, "lpips": 0.182},
        "far": {"views": 5, "psnr": 19.02, "ssim": 0.702, "lpips": 0.413},
        "all": {"views": 12, "psnr": 23.33, "ssim": 0.801, "lpips": 0.278},
    }

    report = accuracy_report(twin(), read_sheet(sheet()), heldout)
    text = markdown(report)

    assert report["render_quality"]["far"]["psnr"] == 19.02
    assert "| Near the capture path | 7 | 26.41 | 0.871 | 0.182 |" in text
    assert "| Far from the capture path | 5 | 19.02 | 0.702 | 0.413 |" in text


def test_a_split_with_no_far_views_shows_an_empty_row() -> None:
    heldout = {
        "near": {"views": 3, "psnr": 25.0, "ssim": 0.8, "lpips": 0.2},
        "far": {"views": 0},
        "all": {"views": 3, "psnr": 25.0, "ssim": 0.8, "lpips": 0.2},
    }

    text = markdown(accuracy_report(twin(), read_sheet(sheet()), heldout))

    assert "| Far from the capture path | 0 | | | |" in text


def test_a_report_without_a_splat_score_has_no_render_section() -> None:
    assert "Render quality" not in markdown(accuracy_report(twin(), read_sheet(sheet())))
