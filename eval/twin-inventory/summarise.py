"""Tables for REPORT.md from the inventory eval results (results/*.json)."""

import json
import sys
from collections import defaultdict
from pathlib import Path

TYPES = ("furniture", "fixture", "wall_item", "textile", "decor", "built_in", "all")


def main(folder: Path) -> None:
    runs: dict[str, list[dict]] = defaultdict(list)
    for path in sorted(folder.glob("*.json")):
        result = json.loads(path.read_text())
        runs[result["detectors"]].append(result)

    def pooled(results: list[dict], stage: str, kind: str) -> tuple[int, int, float]:
        items = found = hand = hit = 0
        for r in results:
            for item in r["recall"]["per_item"]:
                if kind not in ("all", item["type"]):
                    continue
                items += 1
                hand += item["hand"]
                found += item[stage] > 0
                hit += min(item["hand"], item[stage])
        return found, items, hit / hand if hand else 0.0

    first = next(iter(runs.values()))
    print("Listed by the vision models (same for every detector):\n")
    print("| Type | Items listed | Instance recall |\n| --- | --- | --- |")
    for kind in TYPES:
        found, items, inst = pooled(first, "listed", kind)
        if items:
            print(f"| {kind} | {found} of {items} | {inst:.2f} |")
    print("\nPlaced in 3D, per detector (items with at least one object; instance recall):\n")
    names = sorted(runs)
    print("| Type | " + " | ".join(names) + " |\n| --- |" + " --- |" * len(names))
    for kind in TYPES:
        cells = []
        for name in names:
            found, items, inst = pooled(runs[name], "placed", kind)
            cells.append(f"{found} of {items}, {inst:.2f}")
        print(f"| {kind} | " + " | ".join(cells) + " |")
    print("\nObjects placed against items in the rooms (over 1.0 means duplicates or extras):\n")
    print("| Detector | Hand instances | Placed objects | Ratio | Unplaced, flagged | Cost, Rs |")
    print("| --- | --- | --- | --- | --- | --- |")
    for name in names:
        hand = sum(r["recall"]["hand_total"] for r in runs[name])
        placed = sum(r["recall"]["placed_total"] for r in runs[name])
        flagged = sum(len(r["placement"]["unplaced"]) for r in runs[name])
        cost = sum(r["charged_micro_inr"] for r in runs[name]) / 1e6
        print(f"| {name} | {hand} | {placed} | {placed / hand:.1f} | {flagged} | {cost:.0f} |")
    print("\nPer room, all types (listed; placed per detector):\n")
    print("| Room | Listed | " + " | ".join(names) + " |\n| --- | --- |" + " --- |" * len(names))
    for r in first:
        row = [r["scene"], r["recall"]["listed"]["all"]["items"]]
        for name in names:
            match = next(x for x in runs[name] if x["scene"] == r["scene"])
            row.append(match["recall"]["placed"]["all"]["items"])
        print("| " + " | ".join(row) + " |")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
