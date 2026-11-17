"""Build the blind voting set: images with opaque ids, a manifest for the page, and a
private key (id -> design, arm) kept in the repo for analysis.

    python services/spikes/render-bakeoff/local/voting.py OUT_DIR [arms...]

OUT_DIR receives img/<id>.jpg and manifest.json (published with the page);
eval/render-bakeoff/voting/key.json is written in the repo (not published).
"""

from __future__ import annotations

import hashlib
import json
import secrets
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
COMPARISON_ONLY = {"B_gemini"}
ARMS = ["A", "C1_qwen", "C2_qwen", "C3_qwen", "C3L_qwen", "B_qwen", "B_gemini"]
STUDY = "s2"  # s1 used the earlier product set; its key is kept as key_s1.json
# The ARKit bedroom is left out: its capture has no frame that shows the design zone
# (close-ups only), so every arm would render it equally badly.
VOTE_ROOMS = [
    "arkit_living_41159566",
    "frl_apartment_0",
    "arkit_living_41159541",
    "arkit_living_47331265",
]


def fetch(room: str, design: str, arm: str, dst: Path) -> bool:
    r = subprocess.run(
        [
            "modal",
            "volume",
            "get",
            "--force",
            "sajao-render-bakeoff",
            f"renders/{room}/{design}/{arm}/image.png",
            str(dst),
        ],
        capture_output=True,
        text=True,
    )
    return r.returncode == 0 and dst.exists()


def main(out: Path, arms: list[str]) -> None:
    import cv2

    rooms = {}
    for f in sorted((REPO / "eval" / "render-bakeoff" / "designs").glob("*.json")):
        if not f.name.endswith(".designs.json") and f.stem in VOTE_ROOMS:
            rooms[f.stem] = json.loads(f.read_text())
    (out / "img").mkdir(parents=True, exist_ok=True)
    salt = secrets.token_hex(8)
    images, key = [], []
    with tempfile.TemporaryDirectory() as tmp:
        for room, rf in rooms.items():
            for d in rf["designs"]:
                group = hashlib.sha256(f"{salt}{room}{d['id']}".encode()).hexdigest()[:8]
                for arm in arms:
                    src = Path(tmp) / f"{room}_{d['id']}_{arm}.png"
                    if not fetch(room, d["id"], arm, src):
                        continue
                    img = cv2.imread(str(src))
                    s = 1200 / img.shape[1]
                    img = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
                    iid = hashlib.sha256(f"{salt}{room}{d['id']}{arm}".encode()).hexdigest()[:12]
                    cv2.imwrite(
                        str(out / "img" / f"{iid}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 86]
                    )
                    images.append({"id": iid, "file": f"img/{iid}.jpg", "group": group})
                    key.append(
                        {
                            "id": iid,
                            "room": room,
                            "design": d["id"],
                            "slot": d["slot"],
                            "arm": arm,
                            # Gemini is ruled out for placing real products; its renders show
                            # the earlier product set and are kept for comparison only.
                            "comparison_only": arm in COMPARISON_ONLY,
                        }
                    )
    # Shuffle so the manifest order says nothing about the arm.
    order = sorted(range(len(images)), key=lambda i: images[i]["id"])
    images = [images[i] for i in order]
    key = [key[i] for i in order]
    groups = len({x["group"] for x in images})
    manifest = {"study": STUDY, "groups_per_voter": min(groups, 6), "images": images}
    (out / "manifest.json").write_text(json.dumps(manifest))
    kdir = REPO / "eval" / "render-bakeoff" / "voting"
    (kdir / f"key_{STUDY}.json").write_text(json.dumps({"study": STUDY, "images": key}, indent=1))
    (kdir / "key.json").write_text(json.dumps({"study": STUDY, "images": key}, indent=1))
    print(len(images), "images in", groups, "designs")


if __name__ == "__main__":
    main(Path(sys.argv[1]), sys.argv[2:] or ARMS)
