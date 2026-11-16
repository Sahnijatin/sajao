"""Reader for the capture package's depth file (format SJDEPTH1).

The phone writes one file with a depth image per keyframe: LiDAR scene depth
on iPhone, the ARCore depth API on Android. Layout, little endian:

- magic ``SJDEPTH1``, then ``uint32`` entry count;
- per entry: ``uint16`` id length, the keyframe id in UTF-8 (``k1``, ``k2``,
  ...), ``uint32`` width, ``uint32`` height, ``uint16`` millimetres per pixel
  (0 means no reading), ``uint8`` confidence per pixel (0 to 255), row-major.

Each image is aligned to its keyframe as stored (sensor orientation), so its
intrinsics are the keyframe's scaled by ``width / keyframe width``. Depth is
a measurement from the phone's sensor, never from a generative model.
"""

from __future__ import annotations

import struct
import sys
from array import array
from dataclasses import dataclass

MAGIC = b"SJDEPTH1"


class DepthFormatError(ValueError):
    """The file is not a valid SJDEPTH1 depth file."""


@dataclass(frozen=True)
class DepthImage:
    keyframe_id: str
    width: int
    height: int
    millimetres: array[int]  # array("H"), row-major
    confidence: bytes

    def metres_at(self, x: int, y: int) -> float | None:
        """Depth at a pixel in metres, or None where the phone had no reading."""
        value = self.millimetres[y * self.width + x]
        return value / 1000 if value else None


def read_depth(data: bytes) -> dict[str, DepthImage]:
    """Parse a depth file into images keyed by keyframe id."""
    if data[:8] != MAGIC:
        raise DepthFormatError("not an SJDEPTH1 file")
    offset = 8

    def take(size: int) -> bytes:
        nonlocal offset
        if offset + size > len(data):
            raise DepthFormatError("depth file is truncated")
        chunk = data[offset : offset + size]
        offset += size
        return chunk

    (count,) = struct.unpack("<I", take(4))
    images: dict[str, DepthImage] = {}
    for _ in range(count):
        (id_length,) = struct.unpack("<H", take(2))
        keyframe_id = take(id_length).decode("utf-8")
        width, height = struct.unpack("<II", take(8))
        pixels = width * height
        millimetres: array[int] = array("H")
        millimetres.frombytes(take(pixels * 2))
        if sys.byteorder == "big":
            millimetres.byteswap()
        confidence = take(pixels)
        if keyframe_id in images:
            raise DepthFormatError(f"keyframe {keyframe_id} appears twice")
        images[keyframe_id] = DepthImage(keyframe_id, width, height, millimetres, confidence)
    if offset != len(data):
        raise DepthFormatError("trailing bytes after the last depth image")
    return images
