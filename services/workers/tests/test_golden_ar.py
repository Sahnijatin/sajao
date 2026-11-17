"""The phone's AR measurements scored against the tape sheet."""

import json
from pathlib import Path
from typing import Any

import pytest

from sajao_workers.ar_measurements import measure
from sajao_workers.golden import read_sheet
from sajao_workers.golden_ar import ar_markdown, ar_report, run
from sajao_workers.plane_fixtures import DEPTH, FLOOR_Y, HEIGHT, WIDTH, horizontal, room, vertical


def sheet(**change: Any) -> dict[str, Any]:
    """The tape for the 4.2 by 3.4 m test room, a few centimetres off the AR values."""
    base: dict[str, Any] = {
        "room": "Test bedroom 1",
        "unit": "cm",
        # Clockwise from the door, which is on a short wall.
        "walls": {"W1": 338, "W2": 423, "W3": 342, "W4": 417},
        "ceiling": [288, 290],
        "doors": [{"wall": "W1", "width": 88, "height": 207, "offset": 32}],
        "windows": [{"wall": "W2", "width": 118, "height": 123, "sill": 88, "offset": 143}],
        "furniture": [],
    }
    base.update(change)
    return base


def scan(*extra: dict[str, Any]) -> dict[str, Any]:
    door = vertical((0.0, 0.75), 0, 0.9, 0.0, 2.05, "door")
    window = vertical((2.0, DEPTH), -90, 1.2, 0.9, 2.1, "window")
    ceiling = horizontal((2, 1.5), (1.5, 1.5), FLOOR_Y + HEIGHT, classification="ceiling")
    return room(door, window, ceiling, *extra)


def test_every_wall_the_ceiling_and_the_floor_are_scored_against_the_tape() -> None:
    report = ar_report(measure(scan()), read_sheet(sheet()))

    walls = {w["tape"]: w for w in report["walls"]}
    assert sorted(walls) == ["W1", "W2", "W3", "W4"]
    assert walls["W1"]["error_m"] == pytest.approx(DEPTH - 3.38)  # AR minus tape
    assert walls["W2"]["error_m"] == pytest.approx(WIDTH - 4.23)
    assert all(w["basis"] == "corner_to_corner" for w in walls.values())

    assert report["ceiling"]["error_m"] == pytest.approx(HEIGHT - 2.89)
    assert report["floor"]["width"]["tape_m"] == pytest.approx(4.2)
    assert report["floor"]["depth"]["tape_m"] == pytest.approx(3.4)
    assert report["floor"]["area_error_pct"] == pytest.approx(0.0, abs=0.1)

    summary = report["summary"]
    assert summary["walls_measured"] == "4 of 4"
    assert summary["walls_not_found"] == []
    assert summary["largest_wall_error_m"] == pytest.approx(0.03)
    assert summary["dimension_error_pct"] == pytest.approx(0.6, abs=0.2)


def test_doors_and_windows_are_scored_on_width_height_sill_and_distance_from_the_corner() -> None:
    report = ar_report(measure(scan()), read_sheet(sheet()))
    door, window = report["openings"]
    assert (door["found"], window["found"]) == (True, True)
    assert door["width_error_m"] == pytest.approx(0.02)
    assert door["height_error_m"] == pytest.approx(-0.02)
    assert door["offset_error_m"] == pytest.approx(-0.02)
    assert window["sill_error_m"] == pytest.approx(0.02)
    assert window["offset_error_m"] == pytest.approx(-0.03)
    assert report["summary"]["openings_found"] == "2 of 2"
    assert report["summary"]["largest_opening_error_m"] == pytest.approx(0.03)


def test_a_wall_seen_in_part_is_listed_but_kept_out_of_the_error() -> None:
    doc = scan()
    doc["planes"] = [p for p in doc["planes"] if p["transform"][12] != 0.0]  # lose one wall
    report = ar_report(measure(doc), read_sheet(sheet()))

    assert report["summary"]["walls_measured"] == "1 of 4"
    assert report["summary"]["walls_seen_in_part"] == 2
    assert len(report["summary"]["walls_not_found"]) == 1
    partial = [w for w in report["walls"] if w["basis"] == "seen"]
    assert all(w["error_m"] < 0 and not w["within_band"] for w in partial)
    # Only the wall measured corner to corner counts.
    assert report["summary"]["largest_wall_error_m"] == pytest.approx(0.02, abs=0.021)
    assert report["floor"] is None
    assert any("not a floor size" in note for note in report["notes"])


def test_a_scan_with_no_planes_reports_nothing_measured() -> None:
    report = ar_report(measure({"planes": []}), read_sheet(sheet()))
    summary = report["summary"]
    assert summary["dimension_error_pct"] is None
    assert summary["walls_measured"] == "0 of 4"
    assert summary["walls_not_found"] == ["W1", "W2", "W3", "W4"]
    assert summary["openings_found"] == "0 of 2"
    text = ar_markdown(report)
    assert "not measured" in text and "no planes" in text


def test_an_android_scan_has_walls_but_no_doors_or_windows() -> None:
    ceiling = horizontal((2, 1.5), (2, 2), FLOOR_Y + HEIGHT, kind="horizontal_down")
    report = ar_report(measure(room(ceiling, classed=False)), read_sheet(sheet()))
    assert report["summary"]["walls_measured"] == "4 of 4"
    assert report["summary"]["openings_found"] == "0 of 2"
    assert any("does not class planes" in note for note in report["notes"])


def test_the_command_reads_a_capture_folder_and_writes_the_report(tmp_path: Path) -> None:
    folder = tmp_path / "capture"
    folder.mkdir()
    key = "11111111-1111-4111-8111-111111111111/0123456789abcdef0123456789abcdef.json"
    (folder / "capture.json").write_text(json.dumps({"package": {"planes": key}}))
    # The phone's upload stores the file under its key's name.
    (folder / Path(key).name).write_text(json.dumps(scan()))
    tape = tmp_path / "sheet.json"
    tape.write_text(json.dumps(sheet()))

    text = run(folder, tape, tmp_path / "out")

    assert "# AR measurements against the tape: Test bedroom 1" in text
    assert "| W2 | " in text and "corner to corner" in text
    written = json.loads((tmp_path / "out" / "ar-report.json").read_text())
    assert written["summary"]["walls_measured"] == "4 of 4"
    measurements = json.loads((tmp_path / "out" / "ar-measurements.json").read_text())
    assert measurements["format"] == "sajao-ar-measurements-1"
    assert (tmp_path / "out" / "ar-report.md").read_text() == text


def test_a_capture_without_a_planes_file_still_reports(tmp_path: Path) -> None:
    folder = tmp_path / "capture"
    folder.mkdir()
    (folder / "capture.json").write_text(json.dumps({"package": {}}))
    tape = tmp_path / "sheet.json"
    tape.write_text(json.dumps(sheet()))
    assert "Planes in the capture: 0" in run(folder, tape)


def keyframe_opening(kind: str, wall_id: str, **metres: float) -> dict[str, Any]:
    opening: dict[str, Any] = {"id": f"{kind[0]}1", "kind": kind, "wall_id": wall_id}
    opening["source"] = "keyframes"
    for key, value in metres.items():
        opening[key] = {"value_m": value, "source": "estimated", "error_band_m": 0.05}
    return opening


def test_doors_and_windows_from_keyframes_are_the_ones_scored_when_that_pass_ran() -> None:
    measurements = measure(scan())
    planes = {o["kind"]: o for o in measurements["openings"]}
    measurements["keyframe_openings"] = [
        keyframe_opening("door", planes["door"]["wall_id"], width=0.86, height=2.1, offset=0.3),
        keyframe_opening(
            "window", planes["window"]["wall_id"], width=1.25, height=1.2, sill_height=0.9,
            offset=1.4,
        ),
    ]  # fmt: skip
    report = ar_report(measurements, read_sheet(sheet()))

    assert report["openings_source"] == "keyframes"
    door, window = report["openings"]
    assert door["width_error_m"] == pytest.approx(-0.02)  # 86 cm against the tape's 88
    assert window["width_error_m"] == pytest.approx(0.07)
    # The iPhone's own planes are still scored, and compared with the keyframes.
    assert [o["width_error_m"] for o in report["classed_openings"]] == pytest.approx([0.02, 0.02])
    check = {c["kind"]: c for c in report["cross_check"]}
    assert check["door"]["width_difference_m"] == pytest.approx(-0.04)  # keyframes minus plane
    assert check["window"]["width_difference_m"] == pytest.approx(0.05)
    text = ar_markdown(report)
    assert "found in the keyframes and measured on the wall planes" in text
    assert "Cross-check: keyframes minus the phone's own planes" in text


def test_an_android_scan_gets_its_doors_and_windows_from_keyframes() -> None:
    ceiling = horizontal((2, 1.5), (2, 2), FLOOR_Y + HEIGHT, kind="horizontal_down")
    measurements = measure(room(ceiling, classed=False))
    short_wall = next(w["id"] for w in measurements["walls"] if w["length"]["value_m"] < 4)
    measurements["keyframe_openings"] = [
        keyframe_opening("door", short_wall, width=0.9, height=2.05, offset=0.3)
    ]
    report = ar_report(measurements, read_sheet(sheet()))
    assert report["summary"]["openings_found"] == "1 of 2"
    assert report["openings"][0]["found"] is True
    assert report["classed_openings"] == []
    assert [c["matched"] for c in report["cross_check"]] == [False]


def test_without_a_keyframe_pass_the_report_says_where_doors_and_windows_came_from() -> None:
    report = ar_report(measure(scan()), read_sheet(sheet()))
    assert report["openings_source"] == "planes"
    assert report["cross_check"] == []
    assert "no keyframe pass ran" in ar_markdown(report)
