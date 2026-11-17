"""Golden-room accuracy: a twin against the tape measurements of the same room.

The measurement sheet follows the golden set capture protocol (Notion): walls
W1, W2, ... clockwise from the door, ceiling height in one or more places,
each door and window (wall, width, height, sill, distance from the nearest
corner along its wall) and the big furniture (width, depth, height), all in cm.
A template is in eval/golden/sheet-template.json.

Twin walls are paired with tape walls in the turn and direction that fit best
(and put the tape's doors on twin walls that have doors); errors are twin minus
tape, and each is checked against the twin's own error band.
"""

import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from sajao_workers.twin.fusion import GROUPS


class SheetError(ValueError):
    """The measurement sheet is incomplete or not in centimetres."""


@dataclass(frozen=True)
class Sheet:
    room: str
    walls: list[float]  # metres, W1 first
    ceiling: list[float]
    doors: list[dict[str, Any]]
    windows: list[dict[str, Any]]
    furniture: list[dict[str, Any]]


def _metres(value: Any, what: str) -> float:
    if not isinstance(value, int | float) or value <= 0:
        raise SheetError(f"{what} must be a positive number of centimetres")
    return round(float(value) / 100.0, 4)


def read_sheet(raw: Mapping[str, Any]) -> Sheet:
    if raw.get("unit") != "cm":
        raise SheetError('the sheet must be in centimetres ("unit": "cm")')
    walls = raw.get("walls") or {}
    if not walls:
        raise SheetError("the sheet has no walls")
    ordered = sorted(walls, key=lambda k: int(str(k).lstrip("Ww") or 0))
    ceiling = [_metres(v, "ceiling") for v in raw.get("ceiling") or []]
    if not ceiling:
        raise SheetError("the sheet has no ceiling height")

    def openings(kind: str) -> list[dict[str, Any]]:
        out = []
        for item in raw.get(kind) or []:
            entry: dict[str, Any] = {"wall": str(item["wall"]).upper()}
            for key in ("width", "height", "sill", "offset"):
                if key in item:
                    entry[key] = _metres(item[key], f"{kind} {key}")
            out.append(entry)
        return out

    furniture = [
        {
            "name": str(item["name"]).lower().strip(),
            **{k: _metres(item[k], f"{item['name']} {k}") for k in ("width", "depth", "height")},
        }
        for item in raw.get("furniture") or []
    ]
    return Sheet(
        room=str(raw.get("room", "")),
        walls=[_metres(walls[k], f"wall {k}") for k in ordered],
        ceiling=ceiling,
        doors=openings("doors"),
        windows=openings("windows"),
        furniture=furniture,
    )


def _check(twin_m: float, tape_m: float, band_m: float) -> dict[str, Any]:
    error = twin_m - tape_m
    return {
        "twin_m": round(twin_m, 3),
        "tape_m": round(tape_m, 3),
        "error_m": round(error, 3),
        "error_pct": round(100 * error / tape_m, 1),
        "band_m": round(band_m, 3),
        "within_band": abs(error) <= band_m + 1e-9,
    }


def _pair_walls(
    twin_walls: Sequence[Mapping[str, Any]],
    sheet: Sheet,
    openings: Sequence[Mapping[str, Any]],
) -> list[int] | None:
    """Twin wall index for each tape wall, or None when the shapes differ."""
    n = len(twin_walls)
    if len(sheet.walls) != n:
        return None
    lengths = [w["length"]["value_m"] for w in twin_walls]
    on_wall = {(o["kind"], o["wall_id"]) for o in openings}
    tape_openings = [("door", d["wall"]) for d in sheet.doors] + [
        ("window", w["wall"]) for w in sheet.windows
    ]
    best: tuple[float, list[int]] | None = None
    for direction in (1, -1):
        for start in range(n):
            order = [(start + direction * i) % n for i in range(n)]
            cost = sum(abs(lengths[t] - m) for t, m in zip(order, sheet.walls, strict=True))
            for kind, wall in tape_openings:
                index = int(wall.lstrip("W")) - 1
                if 0 <= index < n and (kind, twin_walls[order[index]]["id"]) not in on_wall:
                    cost += 0.25  # prefer the pairing that puts doors and windows on the same wall
            if best is None or cost < best[0] - 1e-9:
                best = (cost, order)
    return best[1] if best else None


def _sides(box: Mapping[str, Any]) -> dict[str, tuple[float, float]]:
    return {k: (box[k]["value_m"], box[k]["error_band_m"]) for k in ("width", "depth", "height")}


def accuracy_report(
    twin: Mapping[str, Any],
    sheet: Sheet,
    truth: Sequence[Mapping[str, Any]] | None = None,
    to_space: Any = None,
) -> dict[str, Any]:
    """The twin against the tape; with `truth` (an annotated dataset room) also its
    box sizes against the ground-truth boxes."""
    shell = twin["shell"]
    walls = shell["walls"]
    notes: list[str] = []
    order = _pair_walls(walls, sheet, shell["openings"])
    wall_rows = []
    if order is None:
        notes.append(
            f"The tape has {len(sheet.walls)} walls and the twin {len(walls)}: walls are not "
            "compared one by one until the shell fits rooms that are not rectangles."
        )
    else:
        for i, twin_index in enumerate(order):
            w = walls[twin_index]
            row = _check(w["length"]["value_m"], sheet.walls[i], w["length"]["error_band_m"])
            wall_rows.append({"tape": f"W{i + 1}", "twin": w["id"], **row})

    ceiling = shell["ceiling_height"]
    ceiling_row = _check(
        ceiling["value_m"], statistics.mean(sheet.ceiling), ceiling["error_band_m"]
    )

    opening_rows = []
    wall_of = {f"W{i + 1}": walls[t]["id"] for i, t in enumerate(order)} if order else {}
    used: set[str] = set()
    for kind, items in (("door", sheet.doors), ("window", sheet.windows)):
        for item in items:
            candidates = [
                o
                for o in shell["openings"]
                if o["kind"] == kind
                and o["id"] not in used
                and (not wall_of or o["wall_id"] == wall_of.get(item["wall"]))
            ]
            match = min(
                candidates,
                key=lambda o: abs(o["width"]["value_m"] - item.get("width", 0)),
                default=None,
            )
            found: dict[str, Any] = {"kind": kind, "tape_wall": item["wall"], "found": bool(match)}
            if match:
                used.add(match["id"])
                found["twin"] = match["id"]
                for key, twin_key in (("width", "width"), ("height", "height"),
                                      ("offset", "offset"), ("sill", "sill_height")):  # fmt: skip
                    if key in item and twin_key in match:
                        found[f"{key}_error_m"] = round(match[twin_key]["value_m"] - item[key], 3)
            opening_rows.append(found)

    furniture_rows = []
    taken: set[str] = set()
    for item in sheet.furniture:
        group = GROUPS.get(item["name"], item["name"])
        candidates = [
            o
            for o in twin["objects"]
            if o["id"] not in taken and GROUPS.get(o["category"], o["category"]) == group
        ]

        def mismatch(o: Mapping[str, Any], item: Mapping[str, Any] = item) -> float:
            s = _sides(o["box"])
            return float(sum(abs(s[k][0] - item[k]) for k in ("width", "depth", "height")))

        match = min(candidates, key=mismatch, default=None)
        item_row: dict[str, Any] = {"name": item["name"], "found": bool(match)}
        if match:
            taken.add(match["id"])
            sides = _sides(match["box"])
            # The twin's width is its longer side: compare like with like.
            longer, shorter = sorted((item["width"], item["depth"]), reverse=True)
            tape = {"width": longer, "depth": shorter, "height": item["height"]}
            checks = {k: _check(sides[k][0], tape[k], sides[k][1]) for k in sides}
            item_row.update(
                twin=match["id"],
                errors_m={k: c["error_m"] for k, c in checks.items()},
                errors_pct={k: c["error_pct"] for k, c in checks.items()},
                within_band=all(c["within_band"] for c in checks.values()),
            )
        furniture_rows.append(item_row)

    dims = [abs(r["error_pct"]) for r in wall_rows] + [abs(ceiling_row["error_pct"])]
    sizes = [abs(v) for r in furniture_rows if r["found"] for v in r["errors_pct"].values()]
    openings_total = len(opening_rows)
    summary = {
        "dimension_error_pct": round(statistics.median(dims), 1),
        "walls_within_band": f"{sum(r['within_band'] for r in wall_rows)} of {len(wall_rows)}",
        "ceiling_within_band": ceiling_row["within_band"],
        "openings_found": f"{sum(r['found'] for r in opening_rows)} of {openings_total}",
        "furniture_found": f"{sum(r['found'] for r in furniture_rows)} of {len(furniture_rows)}",
        "furniture_size_error_pct": round(statistics.median(sizes), 1) if sizes else None,
    }
    return {
        "room": sheet.room,
        "summary": summary,
        "walls": wall_rows,
        "ceiling": ceiling_row,
        "openings": opening_rows,
        "furniture": furniture_rows,
        "inventory": inventory_recall(twin),
        "ground_truth": ground_truth_sizes(twin, truth, to_space) if truth else None,
        "notes": notes,
    }


def _cm(metres: float | None) -> str:
    return "" if metres is None else f"{metres * 100:+.0f}"


def markdown(report: Mapping[str, Any]) -> str:
    s = report["summary"]
    lines = [
        f"# Golden room: {report['room']}",
        "",
        f"- Dimension error (median of walls and ceiling): {s['dimension_error_pct']}%",
        f"- Walls within the twin's error band: {s['walls_within_band']}; "
        f"ceiling: {'yes' if s['ceiling_within_band'] else 'no'}",
        f"- Doors and windows found: {s['openings_found']}",
        f"- Furniture found: {s['furniture_found']}; median size error: "
        f"{s['furniture_size_error_pct']}%",
        "",
        "## Walls and ceiling (error = twin minus tape, cm)",
        "",
        "| Tape | Twin | Tape cm | Twin cm | Error cm | Error % | Band cm | Within |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    rows = [*report["walls"], {"tape": "Ceiling", "twin": "ceiling", **report["ceiling"]}]
    for r in rows:
        lines.append(
            f"| {r['tape']} | {r['twin']} | {r['tape_m'] * 100:.0f} | {r['twin_m'] * 100:.0f} "
            f"| {_cm(r['error_m'])} | {r['error_pct']:+.1f} | {r['band_m'] * 100:.0f} "
            f"| {'yes' if r['within_band'] else 'no'} |"
        )
    lines += ["", "## Doors and windows", "", "| Kind | Tape wall | Found | Width error cm |",
              "| --- | --- | --- | --- |"]  # fmt: skip
    for o in report["openings"]:
        lines.append(
            f"| {o['kind']} | {o['tape_wall']} | {'yes' if o['found'] else 'no'} "
            f"| {_cm(o.get('width_error_m'))} |"
        )
    lines += ["", "## Furniture", "", "| Item | Found | Width % | Depth % | Height % | Within |",
              "| --- | --- | --- | --- | --- | --- |"]  # fmt: skip
    for f in report["furniture"]:
        pct = f.get("errors_pct", {})
        lines.append(
            f"| {f['name']} | {'yes' if f['found'] else 'no'} "
            + " ".join(
                f"| {pct[k]:+.1f}" if k in pct else "|" for k in ("width", "depth", "height")
            )
            + f" | {'yes' if f.get('within_band') else 'no'} |"
        )
    inventory = report.get("inventory")
    if inventory:
        lines += [
            "",
            "## Objects against the listed inventory",
            "",
            f"Listed by {', '.join(inventory['listed_by'])}: {inventory['listed']} items; "
            f"placed in 3D: {inventory['placed']} (recall {inventory['recall']:.2f}).",
            "",
            "| Type | Listed | Placed | Recall |",
            "| --- | --- | --- | --- |",
            *[f"| {k} | {v['listed']} | {v['placed']} | {v['recall']:.2f} |"
              for k, v in inventory["by_type"].items()],
        ]  # fmt: skip
        if inventory["unplaced"]:
            lines += ["", "Not placed (kept in the twin, flagged):", "",
                      "| Item | Type | Why | Tried |", "| --- | --- | --- | --- |"]  # fmt: skip
            for u in inventory["unplaced"]:
                lines.append(
                    f"| {u['name']} | {u['type']} | {u['reason'].replace('_', ' ')} "
                    f"| {'; '.join(u['tried'])} |"
                )
    truth = report.get("ground_truth")
    if truth:
        t = truth["summary"]
        lines += [
            "",
            "## Box sizes against ground truth",
            "",
            f"Matched {t['matched']} annotated boxes; median size error "
            f"{t['median_size_error_pct']}%; within the twin's band: {t['within_band']}.",
            "",
            "| Ground truth | Twin | Width % | Depth % | Height % | Centre off m | Within |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
        for row in truth["boxes"]:
            if not row["twin"]:
                lines.append(f"| {row['label']} | not found | | | | | |")
                continue
            pct = row["error_pct"]
            lines.append(
                f"| {row['label']} | {row['twin']} | {pct['width']:+.1f} | {pct['depth']:+.1f} "
                f"| {pct['height']:+.1f} | {row['centre_error_m']:.2f} "
                f"| {'yes' if row['within_band'] else 'no'} |"
            )
    if report["notes"]:
        lines += ["", "## Notes", "", *[f"- {n}" for n in report["notes"]]]
    return "\n".join(lines) + "\n"


def inventory_recall(twin: Mapping[str, Any]) -> dict[str, Any] | None:
    """Of the items the vision models listed, how many were placed in 3D, per type.

    Placed items are the distinct categories among the twin's objects (by their
    type) and built-ins; the rest are the inventory's unplaced items, each kept
    with what was tried and why it failed."""
    inventory = twin.get("inventory")
    if inventory is None:
        return None
    placed: dict[str, set[str]] = {}
    for obj in twin["objects"]:
        placed.setdefault(obj.get("object_type", "furniture"), set()).add(obj["category"])
    for built_in in twin["shell"].get("built_ins", []):
        placed.setdefault("built_in", set()).add(built_in["category"])
    unplaced = list(inventory["unplaced"])
    missing: dict[str, int] = {}
    for item in unplaced:
        missing[item["type"]] = missing.get(item["type"], 0) + 1
    by_type = {}
    for kind in sorted(set(placed) | set(missing)):
        found = len(placed.get(kind, set()))
        listed = found + missing.get(kind, 0)
        by_type[kind] = {"listed": listed, "placed": found, "recall": round(found / listed, 2)}
    total_placed = sum(len(v) for v in placed.values())
    return {
        "listed_by": list(inventory["listed_by"]),
        "listed": int(inventory["items_listed"]),
        "placed": total_placed,
        "recall": round(total_placed / max(1, int(inventory["items_listed"])), 2),
        "by_type": by_type,
        "unplaced": [{k: u[k] for k in ("name", "type", "reason", "tried")} for u in unplaced],
    }


def _group(name: str) -> str:
    key = name.lower().replace("_", " ").strip()
    key = GROUPS.get(key, key)
    head = key.split(" ")[-1]
    head = {"monitor": "television", "tv": "television"}.get(head, head)
    return GROUPS.get(head, head)


def ground_truth_sizes(
    twin: Mapping[str, Any], truth: Sequence[Mapping[str, Any]], to_space: Any
) -> dict[str, Any]:
    """Box sizes against ground-truth boxes (an annotated dataset room).

    `truth` boxes are {label, center, size_m: [longer, shorter, height]} in the
    capture's AR world; `to_space` (4x4) maps that world to the twin's space. A
    twin object matches the nearest ground-truth box of the same kind within
    half its diagonal (at least 0.5 m), one to one."""
    import numpy as np

    objects = [*twin["objects"], *twin["shell"].get("built_ins", [])]
    used: set[str] = set()
    rows = []
    for gt in truth:
        centre = np.asarray(to_space, dtype=np.float64) @ np.array([*gt["center"], 1.0])
        reach = max(0.5, 0.5 * float(np.hypot(gt["size_m"][0], gt["size_m"][1])))
        best, best_d = None, reach
        for obj in objects:
            if obj["id"] in used or _group(obj["category"]) != _group(gt["label"]):
                continue
            c = obj["box"]["center"]
            d = float(np.hypot(c["x_m"] - centre[0], c["y_m"] - centre[1]))
            if d <= best_d:
                best, best_d = obj, d
        row: dict[str, Any] = {"label": gt["label"], "twin": best["id"] if best else None}
        if best is not None:
            used.add(best["id"])
            box = best["box"]
            sides = {"width": box["width"], "depth": box["depth"], "height": box["height"]}
            tape = dict(zip(("width", "depth", "height"), gt["size_m"], strict=True))
            checks = {k: _check(sides[k]["value_m"], tape[k], sides[k]["error_band_m"])
                      for k in sides}  # fmt: skip
            row.update(
                category=best["category"],
                centre_error_m=round(best_d, 2),
                error_pct={k: c["error_pct"] for k, c in checks.items()},
                within_band=all(c["within_band"] for c in checks.values()),
            )
        rows.append(row)
    matched = [r for r in rows if r["twin"]]
    errors = [abs(v) for r in matched for v in r["error_pct"].values()]
    return {
        "boxes": rows,
        "summary": {
            "matched": f"{len(matched)} of {len(rows)}",
            "median_size_error_pct": round(statistics.median(errors), 1) if errors else None,
            "within_band": f"{sum(r['within_band'] for r in matched)} of {len(matched)}",
        },
    }
