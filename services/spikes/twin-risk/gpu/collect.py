"""Copy small results (JSON and images) from the Modal volume into eval/twin-risk/.

Large files (splats, PLY variants, frames) stay on the volume. Run from the repo
root after the stages finish: python services/spikes/twin-risk/gpu/collect.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
DEST = ROOT / "eval" / "twin-risk"
VOLUME = "sajao-twin-risk"
JSON = [
    "timings.json",
    "segment_gdino.json",
    "segment_yoloe.json",
    "mapanything.json",
    "objects_gdino_lidar.json",
    "objects_gdino_mapanything.json",
    "objects_yoloe_lidar.json",
    "objects_yoloe_mapanything.json",
    "objects_gdino_lidar_refined.json",
    "objects_gdino_mapanything_refined.json",
    "objects_yoloe_lidar_refined.json",
    "objects_yoloe_mapanything_refined.json",
    "splat.json",
    "edit.json",
    "phone_variants.json",
    "stream.json",
    "light_mesh.json",
]


def get(remote: str, local: Path) -> bool:
    local.parent.mkdir(parents=True, exist_ok=True)
    res = subprocess.run(
        ["modal", "volume", "get", "--force", VOLUME, remote, str(local)],
        capture_output=True,
        text=True,
    )
    return res.returncode == 0


def ls(remote: str) -> list[str]:
    res = subprocess.run(["modal", "volume", "ls", VOLUME, remote], capture_output=True, text=True)
    return [x.strip() for x in res.stdout.splitlines() if x.strip().startswith("out/")]


def images_under(remote: str) -> list[str]:
    """Image files under a remote folder, recursing into subfolders."""
    out = []
    for entry in ls(remote):
        if entry.endswith((".jpg", ".png")):
            out.append(entry)
        elif "." not in Path(entry).name:
            out.extend(images_under(entry))
    return out


def main(scenes: list[str]) -> None:
    for scene in scenes:
        for name in JSON:
            get(f"out/{scene}/{name}", DEST / "results" / scene / name)
        top = ls(f"out/{scene}")
        files = [x for x in top if x.endswith(".png")]
        for sub in ("splat", "edit"):
            files += images_under(f"out/{scene}/{sub}")
        for remote in files:
            rel = Path(remote).relative_to(f"out/{scene}")
            get(remote, DEST / "images" / scene / rel)
        print(f"collected {scene}: {len(files)} images")


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from app import ALL

    main(sys.argv[1:] or ALL)
