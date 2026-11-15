"""Copy small results (JSON and images) from the Modal volume into eval/twin-risk/.

Large files (splats, PLY variants, frames) stay on the volume. Run from the repo
root after the stages finish: python services/spikes/twin-risk/gpu/collect.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
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
IMAGES = [
    "topdown_gdino_lidar.png",
    "topdown_gdino_mapanything.png",
    "topdown_yoloe_lidar.png",
    "topdown_yoloe_mapanything.png",
    "topdown_gdino_lidar_refined.png",
    "topdown_yoloe_lidar_refined.png",
    "splat/test_0.jpg",
    "edit",
]


def get(remote: str, local: Path) -> bool:
    local.parent.mkdir(parents=True, exist_ok=True)
    res = subprocess.run(
        ["modal", "volume", "get", "--force", VOLUME, remote, str(local)],
        capture_output=True,
        text=True,
    )
    return res.returncode == 0


def main(scenes: list[str]) -> None:
    for scene in scenes:
        for name in JSON:
            get(f"out/{scene}/{name}", DEST / "results" / scene / name)
        for name in IMAGES:
            with tempfile.TemporaryDirectory() as tmp:
                if not get(f"out/{scene}/{name}", Path(tmp) / "x"):
                    continue
                src = Path(tmp) / "x"
                files = [src] if src.is_file() else sorted(src.rglob("*"))
                for f in files:
                    if f.is_file() and f.suffix.lower() in (".jpg", ".png"):
                        rel = Path(name) / f.relative_to(src) if src.is_dir() else Path(name).name
                        dst = DEST / "images" / scene / rel
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy(f, dst)
        print(f"collected {scene}")


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from app import ALL

    main(sys.argv[1:] or ALL)
