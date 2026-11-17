"""Golden-room accuracy of the phone's AR measurements against the tape.

Fit is checked against what the phone measured, so this report asks one
thing of a scan: how far are its walls, floor, ceiling, doors and windows
from the tape? It needs no GPU and no twin: the capture's planes file goes
through `ar_measurements.measure` and the result is scored against the same
measurement sheet the twin's report uses (eval/golden).

    python -m sajao_workers.golden_ar --capture path/to/capture --tape path/to/sheet.json

Errors are AR minus tape. A wall the phone saw only in part is a lower bound,
not a measurement: it is listed with how much is missing and kept out of the
error figures.
"""

import argparse
import itertools
import json
import statistics
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from sajao_workers.ar_measurements import measure
from sajao_workers.ar_openings import cross_check
from sajao_workers.golden import Sheet, _check, read_sheet

# Pairing more walls than this by trying every order would take too long.
MAX_WALLS = 12


def _pair(
    walls: Sequence[Mapping[str, Any]], openings: Sequence[Mapping[str, Any]], sheet: Sheet
) -> list[tuple[int, int]] | None:
    """(tape index, AR index) pairs, in the turn and direction that fit the lengths best.

    The phone may have found fewer walls than the room has; the walls it found
    still go round the room in order, so they are matched to a run of tape
    walls with gaps. None when it found more walls than the tape lists.
    """
    k, n = len(walls), len(sheet.walls)
    if k == 0 or k > n or n > MAX_WALLS:
        return None
    on_wall = {(o["kind"], o.get("wall_id")) for o in openings}
    tape_openings = [("door", d["wall"]) for d in sheet.doors] + [
        ("window", w["wall"]) for w in sheet.windows
    ]
    best: tuple[float, list[tuple[int, int]]] | None = None
    for subset in itertools.combinations(range(n), k):
        for direction in (1, -1):
            for start in range(k):
                pairs = [(subset[i], (start + direction * i) % k) for i in range(k)]
                cost = 0.0
                for tape_index, ar_index in pairs:
                    wall = walls[ar_index]
                    gap = wall["length"]["value_m"] - sheet.walls[tape_index]
                    # A wall seen in part may be shorter than the tape, never longer.
                    cost += (
                        abs(gap) if wall["basis"] == "corner_to_corner" or gap > 0 else 0.1 * -gap
                    )
                paired = {f"W{t + 1}": walls[a]["id"] for t, a in pairs}
                for kind, tape_wall in tape_openings:
                    if tape_wall in paired and (kind, paired[tape_wall]) not in on_wall:
                        cost += (
                            0.25  # prefer the pairing that puts doors and windows on the same wall
                        )
                if best is None or cost < best[0] - 1e-9:
                    best = (cost, pairs)
    return best[1] if best else None


def _score_openings(
    openings: Sequence[Mapping[str, Any]], sheet: Sheet, wall_of: Mapping[str, str]
) -> list[dict[str, Any]]:
    """Each door and window on the tape, with the measured one that matches it."""
    opening_rows = []
    used: set[str] = set()
    for kind, items in (("door", sheet.doors), ("window", sheet.windows)):
        for item in items:
            candidates = [
                o
                for o in openings
                if o["kind"] == kind
                and o["id"] not in used
                and (
                    o.get("wall_id") is None
                    or item["wall"] not in wall_of
                    or o["wall_id"] == wall_of[item["wall"]]
                )
            ]
            match = min(
                candidates,
                key=lambda o, item=item: abs(o["width"]["value_m"] - item.get("width", 0)),  # type: ignore[misc]
                default=None,
            )
            found: dict[str, Any] = {"kind": kind, "tape_wall": item["wall"], "found": bool(match)}
            if match:
                used.add(match["id"])
                found["ar"] = match["id"]
                for key, ar_key in (("width", "width"), ("height", "height"),
                                    ("offset", "offset"), ("sill", "sill_height")):  # fmt: skip
                    if key in item and ar_key in match:
                        found[f"{key}_error_m"] = round(match[ar_key]["value_m"] - item[key], 3)
            opening_rows.append(found)
    return opening_rows


def ar_report(measurements: Mapping[str, Any], sheet: Sheet) -> dict[str, Any]:
    notes = list(measurements.get("notes", []))
    openings = list(measurements.get("openings", []))
    walls = list(measurements.get("walls", []))
    pairs = _pair(walls, openings, sheet)
    wall_rows: list[dict[str, Any]] = []
    wall_of: dict[str, str] = {}
    if pairs is None and walls:
        notes.append(
            f"The phone found {len(walls)} walls and the tape lists {len(sheet.walls)}: "
            "walls are not compared one by one."
        )
    for tape_index, ar_index in sorted(pairs or []):
        wall = walls[ar_index]
        row = _check(
            wall["length"]["value_m"], sheet.walls[tape_index], wall["length"]["error_band_m"]
        )
        measured = wall["basis"] == "corner_to_corner"
        if not measured:
            row["within_band"] = False
        wall_rows.append(
            {"tape": f"W{tape_index + 1}", "ar": wall["id"], "basis": wall["basis"], **row}
        )
        wall_of[f"W{tape_index + 1}"] = wall["id"]
    missing = [f"W{i + 1}" for i in range(len(sheet.walls)) if f"W{i + 1}" not in wall_of]

    ceiling_row = None
    ceiling = measurements.get("ceiling_height")
    if ceiling:
        ceiling_row = _check(
            ceiling["value_m"], statistics.mean(sheet.ceiling), ceiling["error_band_m"]
        )

    floor_row = None
    floor = measurements.get("floor")
    if len(sheet.walls) == 4:
        # The tape has no floor size of its own: for a four-wall room it is the
        # mean of each pair of opposite walls.
        sides = sorted(
            ((sheet.walls[0] + sheet.walls[2]) / 2, (sheet.walls[1] + sheet.walls[3]) / 2)
        )
        tape_area = sides[0] * sides[1]
        if floor and floor["basis"] == "corner_to_corner" and "width" in floor:
            floor_row = {
                "width": _check(
                    floor["width"]["value_m"], sides[1], floor["width"]["error_band_m"]
                ),
                "depth": _check(
                    floor["depth"]["value_m"], sides[0], floor["depth"]["error_band_m"]
                ),
                "ar_area_m2": floor["area_m2"],
                "tape_area_m2": round(tape_area, 2),
                "area_error_pct": round(100 * (floor["area_m2"] - tape_area) / tape_area, 1),
            }
        elif floor:
            notes.append(
                f"Floor: the phone saw {floor['area_m2']} m2 of about {tape_area:.2f} m2; "
                "that is not a floor size."
            )

    classed_rows = _score_openings(openings, sheet, wall_of)
    from_keyframes = measurements.get("keyframe_openings")
    if from_keyframes is None:
        # No keyframe pass ran (this command alone has no vision model): the
        # phone's own door and window planes are all there is.
        opening_rows, source = classed_rows, "planes"
    else:
        opening_rows, source = _score_openings(from_keyframes, sheet, wall_of), "keyframes"
    checks = cross_check(openings, from_keyframes) if from_keyframes is not None else []

    measured_rows = [r for r in wall_rows if r["basis"] == "corner_to_corner"]
    errors = [abs(r["error_pct"]) for r in measured_rows]
    if ceiling_row:
        errors.append(abs(ceiling_row["error_pct"]))
    opening_errors = [abs(v) for r in opening_rows for k, v in r.items() if k.endswith("_error_m")]
    within = sum(r["within_band"] for r in measured_rows)
    summary = {
        "dimension_error_pct": round(statistics.median(errors), 1) if errors else None,
        "walls_measured": f"{len(measured_rows)} of {len(sheet.walls)}",
        "walls_seen_in_part": len(wall_rows) - len(measured_rows),
        "walls_not_found": missing,
        "largest_wall_error_m": (max((abs(r["error_m"]) for r in measured_rows), default=None)),
        "walls_within_band": f"{within} of {len(measured_rows)}",
        "ceiling_measured": ceiling_row is not None,
        "floor_measured": floor_row is not None,
        "openings_found": f"{sum(r['found'] for r in opening_rows)} of {len(opening_rows)}",
        "largest_opening_error_m": max(opening_errors, default=None),
    }
    return {
        "room": sheet.room,
        "planes": measurements.get("planes", 0),
        "summary": summary,
        "walls": wall_rows,
        "ceiling": ceiling_row,
        "floor": floor_row,
        "openings": opening_rows,
        # Where the doors and windows above come from: "keyframes" or "planes".
        "openings_source": source,
        # iPhone: the phone's own door and window planes against the tape, and
        # against the keyframe reading of the same opening.
        "classed_openings": classed_rows if source == "keyframes" and openings else [],
        "cross_check": checks,
        "notes": notes,
    }


def _cm(metres: float | None) -> str:
    return "" if metres is None else f"{metres * 100:+.0f}"


def _opening_table(title: str, rows: Sequence[Mapping[str, Any]]) -> list[str]:
    lines = [
        "",
        f"## {title} (error = AR minus tape, cm)",
        "",
        "| Kind | Tape wall | Found | Width | Height | Sill | From corner |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for o in rows:
        lines.append(
            f"| {o['kind']} | {o['tape_wall']} | {'yes' if o['found'] else 'no'} "
            + " ".join(
                f"| {_cm(o.get(f'{key}_error_m'))}" for key in ("width", "height", "sill", "offset")
            )
            + " |"
        )
    return lines


def ar_markdown(report: Mapping[str, Any]) -> str:
    s = report["summary"]
    error = "not measured" if s["dimension_error_pct"] is None else f"{s['dimension_error_pct']}%"
    largest = s["largest_wall_error_m"]
    lines = [
        f"# AR measurements against the tape: {report['room']}",
        "",
        f"- Planes in the capture: {report['planes']}",
        f"- Dimension error (median of measured walls and ceiling): {error}",
        f"- Walls measured corner to corner: {s['walls_measured']}; seen only in part: "
        f"{s['walls_seen_in_part']}; not found: {', '.join(s['walls_not_found']) or 'none'}",
        "- Largest wall error: "
        + ("not measured" if largest is None else f"{largest * 100:.0f} cm"),
        f"- Walls within the error band: {s['walls_within_band']}",
        f"- Ceiling height measured: {'yes' if s['ceiling_measured'] else 'no'}; "
        f"floor size measured: {'yes' if s['floor_measured'] else 'no'}",
        f"- Doors and windows found: {s['openings_found']}",
        "",
        "## Walls and ceiling (error = AR minus tape, cm)",
        "",
        "| Tape | AR | Basis | Tape cm | AR cm | Error cm | Error % | Band cm | Within |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    rows = list(report["walls"])
    if report["ceiling"]:
        rows.append(
            {"tape": "Ceiling", "ar": "ceiling", "basis": "floor to ceiling", **report["ceiling"]}
        )
    for r in rows:
        basis = "seen in part" if r["basis"] == "seen" else r["basis"].replace("_", " ")
        lines.append(
            f"| {r['tape']} | {r['ar']} | {basis} | {r['tape_m'] * 100:.0f} "
            f"| {r['twin_m'] * 100:.0f} | {_cm(r['error_m'])} | {r['error_pct']:+.1f} "
            f"| {r['band_m'] * 100:.0f} | {'yes' if r['within_band'] else 'no'} |"
        )
    floor = report["floor"]
    if floor:
        lines += [
            "",
            "## Floor",
            "",
            "| Side | Tape cm | AR cm | Error cm | Error % |",
            "| --- | --- | --- | --- | --- |",
        ]
        for side in ("width", "depth"):
            r = floor[side]
            lines.append(
                f"| {side} | {r['tape_m'] * 100:.0f} | {r['twin_m'] * 100:.0f} "
                f"| {_cm(r['error_m'])} | {r['error_pct']:+.1f} |"
            )
        lines.append(
            f"\nArea: tape {floor['tape_area_m2']} m2, AR {floor['ar_area_m2']} m2 "
            f"({floor['area_error_pct']:+.1f}%). The tape's floor is the mean of opposite walls."
        )
    how = (
        "found in the keyframes and measured on the wall planes"
        if report["openings_source"] == "keyframes"
        else "from the planes the phone classed itself; no keyframe pass ran"
    )
    lines += _opening_table(f"Doors and windows, {how}", report["openings"])
    if report["classed_openings"]:
        lines += _opening_table(
            "Doors and windows from the planes the phone classed itself",
            report["classed_openings"],
        )
    if report["cross_check"]:
        lines += [
            "",
            "## Cross-check: keyframes minus the phone's own planes, cm",
            "",
            "| Kind | Wall | Phone's plane | Keyframes | Width | Height | Sill | From corner |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for c in report["cross_check"]:
            lines.append(
                f"| {c['kind']} | {c.get('wall_id') or ''} | {c.get('classed', 'not found')} "
                f"| {c.get('keyframes', 'not found')} "
                + " ".join(
                    f"| {_cm(c.get(f'{key}_difference_m'))}"
                    for key in ("width", "height", "sill_height", "offset")
                )
                + " |"
            )
    if report["notes"]:
        lines += ["", "## Notes", "", *[f"- {n}" for n in report["notes"]]]
    return "\n".join(lines) + "\n"


def capture_planes(folder: Path) -> dict[str, Any]:
    """The planes document of an uploaded capture folder; empty when the capture has none."""
    capture = json.loads((folder / "capture.json").read_text())
    key = (capture.get("package") or {}).get("planes")
    if not key:
        return {"format": "sajao-planes-1", "planes": []}
    for path in (folder / key, folder / Path(key).name):
        if path.is_file():
            doc: dict[str, Any] = json.loads(path.read_text())
            return doc
    raise FileNotFoundError(f"{key} is not in the capture folder")


def run(capture: Path, tape: Path, out: Path | None = None) -> str:
    """Measure a capture folder, score it against the sheet, write the files, return the report."""
    sheet = read_sheet(json.loads(tape.read_text()))
    measurements = measure(capture_planes(capture))
    report = ar_report(measurements, sheet)
    text = ar_markdown(report)
    if out is not None:
        out.mkdir(parents=True, exist_ok=True)
        (out / "ar-measurements.json").write_text(json.dumps(measurements, indent=1) + "\n")
        (out / "ar-report.json").write_text(json.dumps(report, indent=1) + "\n")
        (out / "ar-report.md").write_text(text)
    return text


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--capture", type=Path, required=True, help="the uploaded capture folder")
    parser.add_argument("--tape", type=Path, required=True, help="the measurement sheet (cm)")
    parser.add_argument("--out", type=Path, default=None, help="where to write the report files")
    args = parser.parse_args()
    print(run(args.capture, args.tape, args.out))


if __name__ == "__main__":
    main()
