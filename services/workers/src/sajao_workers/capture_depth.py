"""Reader for the capture package's depth file, format SJDEPTH1 (docs/06-room-capture.md).

Little endian: magic "SJDEPTH1", uint32 count, then per keyframe: uint16 id
length, the keyframe id in UTF-8, uint32 width, uint32 height, uint16
millimetres per pixel (0 means no reading), uint8 confidence per pixel.
"""

import struct
from dataclasses import dataclass

import numpy as np

MAGIC = b"SJDEPTH1"
# Confidence is 0 to 255. Only high-confidence readings place points, as in the
# spike (ARKit's high level; ARCore's confidence scaled the same way).
HIGH_CONFIDENCE = 200


@dataclass(frozen=True)
class DepthImage:
    millimetres: np.ndarray  # (H, W) uint16
    confidence: np.ndarray  # (H, W) uint8

    def confident_metres(self) -> np.ndarray:
        metres = self.millimetres.astype(np.float32) / 1000.0
        result: np.ndarray = np.where(self.confidence >= HIGH_CONFIDENCE, metres, 0.0)
        return result.astype(np.float32)


def read_depth_container(data: bytes) -> dict[str, DepthImage]:
    """Depth images by keyframe id. Raises ValueError on a malformed file."""
    if data[: len(MAGIC)] != MAGIC:
        raise ValueError("not an SJDEPTH1 file")
    offset = len(MAGIC)

    def take(n: int) -> bytes:
        nonlocal offset
        if offset + n > len(data):
            raise ValueError("SJDEPTH1 file is truncated")
        chunk = data[offset : offset + n]
        offset += n
        return chunk

    (count,) = struct.unpack("<I", take(4))
    images = {}
    for _ in range(count):
        (id_length,) = struct.unpack("<H", take(2))
        key = take(id_length).decode("utf-8")
        width, height = struct.unpack("<II", take(8))
        pixels = width * height
        millimetres = np.frombuffer(take(2 * pixels), dtype="<u2").reshape(height, width)
        confidence = np.frombuffer(take(pixels), dtype=np.uint8).reshape(height, width)
        images[key] = DepthImage(millimetres.astype(np.uint16), confidence.copy())
    return images
