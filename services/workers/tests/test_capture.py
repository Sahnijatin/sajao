"""Reading the capture package: SJDEPTH1 depth and keyframes into a frames manifest."""

import io
import json
import math
import struct
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from PIL import Image

from sajao_workers.capture_depth import HIGH_CONFIDENCE, read_depth_container
from sajao_workers.steps import LocalArtifactStore
from sajao_workers.twin.capture_frames import CaptureError, frames_manifest
from sajao_workers.twin.objects import decode_depth_mm


def sjdepth(entries: list[tuple[str, np.ndarray, np.ndarray]]) -> bytes:
    """The format as #48's Android writer produces it (docs/06-room-capture.md)."""
    out = bytearray(b"SJDEPTH1") + struct.pack("<I", len(entries))
    for key, mm, conf in entries:
        raw = key.encode()
        h, w = mm.shape
        out += struct.pack("<H", len(raw)) + raw + struct.pack("<II", w, h)
        out += mm.astype("<u2").tobytes() + conf.astype(np.uint8).tobytes()
    return bytes(out)


def test_depth_container_round_trips() -> None:
    mm = np.arange(12, dtype=np.uint16).reshape(3, 4) * 100
    conf = np.full((3, 4), 255, np.uint8)

    depth = read_depth_container(sjdepth([("k1", mm, conf), ("k2", mm + 1, conf)]))

    assert set(depth) == {"k1", "k2"}
    assert depth["k1"].millimetres.shape == (3, 4)
    assert depth["k1"].millimetres[2, 3] == 1100
    assert depth["k2"].millimetres[0, 0] == 1


@pytest.mark.parametrize(
    "data",
    [b"NOTDEPTH" + b"\0" * 8, b"SJDEPTH1" + struct.pack("<I", 1) + b"\x02\x00k1"],  # truncated
)
def test_a_broken_depth_file_is_rejected(data: bytes) -> None:
    with pytest.raises(ValueError):
        read_depth_container(data)


def test_low_confidence_depth_is_dropped() -> None:
    mm = np.full((2, 2), 1500, np.uint16)
    conf = np.array([[255, HIGH_CONFIDENCE - 1], [HIGH_CONFIDENCE, 0]], np.uint8)

    metres = read_depth_container(sjdepth([("k1", mm, conf)]))["k1"].confident_metres()

    assert metres.tolist() == [[1.5, 0.0], [1.5, 0.0]]


def keyframe(i: int, yaw_deg: float = 0.0) -> dict[str, Any]:
    half = math.radians(yaw_deg) / 2
    return {
        "id": f"k{i}",
        "image": f"captures/c1/keyframes/k{i}.jpg",
        "captured_at_ms": 1000 * i,
        "sharpness": 400.0,
        "pose": {
            "position": {"x_m": 0.1 * i, "y_m": 1.4, "z_m": 0.0},
            "rotation": [0.0, math.sin(half), 0.0, math.cos(half)],
        },
        "intrinsics": {
            "fx": 500.0,
            "fy": 500.0,
            "cx": 320.0,
            "cy": 240.0,
            "width_px": 640,
            "height_px": 480,
        },
    }


def package(n: int = 3, lidar: bool = True) -> dict[str, Any]:
    return {
        "ar": {"tracking": "arkit", "lidar": lidar, "depth": True},
        "keyframes": [keyframe(i) for i in range(1, n + 1)],
        "detections": [],
        "sensor_log": "captures/c1/sensors.jsonl",
        "depth": "captures/c1/depth.bin",
    }


def ingest(store: LocalArtifactStore, n: int = 3) -> tuple[dict[str, str], bytes]:
    images = {}
    for i in range(1, n + 1):
        buf = io.BytesIO()
        Image.fromarray(np.full((480, 640, 3), 40 * i, np.uint8)).save(buf, format="JPEG")
        images[f"k{i}"] = store.put_blob(buf.getvalue())
    mm = np.full((192, 256), 2000, np.uint16)
    conf = np.full((192, 256), 255, np.uint8)
    return images, sjdepth([(f"k{i}", mm, conf) for i in range(1, n + 1)])


def test_a_package_becomes_a_frames_manifest(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path)
    images, depth = ingest(store)

    manifest = frames_manifest(package(), images, depth, store)

    assert manifest["up_axis"] == 1
    assert manifest["depth_source"] == "lidar"
    first = manifest["frames"][0]
    assert first["keyframe_id"] == "k1"
    assert first["image"] == images["k1"]
    assert (first["width"], first["height"]) == (640, 480)
    assert first["intrinsics"] == [[500.0, 0.0, 320.0], [0.0, 500.0, 240.0], [0.0, 0.0, 1.0]]
    depth_m = decode_depth_mm(store.read_blob(first["depth"]))
    assert depth_m.shape == (192, 256) and depth_m[0, 0] == pytest.approx(2.0)


def test_ar_poses_become_opencv_cameras(tmp_path: Path) -> None:
    """ARKit camera: +Y up, -Z forward. OpenCV camera: +Y down, +Z forward."""
    store = LocalArtifactStore(tmp_path)
    images, depth = ingest(store, n=1)
    pkg = package(n=1)
    pkg["keyframes"][0] = keyframe(1, yaw_deg=90.0)  # turned left: AR -Z now points to world -X

    c2w = np.asarray(frames_manifest(pkg, images, depth, store)["frames"][0]["c2w"])

    forward = c2w[:3, :3] @ np.array([0.0, 0.0, 1.0])  # OpenCV forward in world
    down = c2w[:3, :3] @ np.array([0.0, 1.0, 0.0])  # OpenCV down in world
    assert np.allclose(forward, [-1.0, 0.0, 0.0], atol=1e-9)
    assert np.allclose(down, [0.0, -1.0, 0.0], atol=1e-9)
    assert np.allclose(c2w[:3, 3], [0.1, 1.4, 0.0])


def test_phones_without_lidar_get_the_wider_image_depth_band(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path)
    images, depth = ingest(store)

    assert frames_manifest(package(lidar=False), images, depth, store)["depth_source"] == "image"


def test_without_depth_the_frames_wait_for_the_depth_step(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path)
    images, _ = ingest(store)
    pkg = package()
    del pkg["depth"]

    manifest = frames_manifest(pkg, images, None, store)

    assert all(frame["depth"] is None for frame in manifest["frames"])
    assert manifest["depth_source"] == "image"


def test_a_capture_without_ar_poses_is_refused(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path)
    images, depth = ingest(store)
    pkg = package()
    pkg["ar"]["tracking"] = "none"
    for frame in pkg["keyframes"]:
        del frame["pose"]

    with pytest.raises(CaptureError, match="poses"):
        frames_manifest(pkg, images, depth, store)


def test_a_missing_keyframe_image_is_refused(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path)
    images, depth = ingest(store)
    del images["k2"]

    with pytest.raises(CaptureError, match="k2"):
        frames_manifest(package(), images, depth, store)


def test_the_manifest_is_stable_json(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path)
    images, depth = ingest(store)

    first = json.dumps(frames_manifest(package(), images, depth, store), sort_keys=True)
    again = json.dumps(frames_manifest(package(), images, depth, store), sort_keys=True)

    assert first == again  # same capture, same step keys downstream
