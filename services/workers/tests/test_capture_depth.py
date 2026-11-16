import struct

import pytest

from sajao_workers.capture_depth import DepthFormatError, read_depth

# The same bytes the Android writer produces in CaptureFormatsTest.depthContainerLayout:
# one 2 by 1 image for keyframe k1, 1.5 m then no reading, confidence 255 then 0.
PHONE_BYTES = (
    b"SJDEPTH1"
    + struct.pack("<I", 1)
    + struct.pack("<H", 2)
    + b"k1"
    + struct.pack("<II", 2, 1)
    + struct.pack("<HH", 1500, 0)
    + bytes([255, 0])
)


def test_reads_what_the_phone_writes() -> None:
    images = read_depth(PHONE_BYTES)
    image = images["k1"]
    assert (image.width, image.height) == (2, 1)
    assert image.metres_at(0, 0) == 1.5
    assert image.metres_at(1, 0) is None
    assert image.confidence == bytes([255, 0])


def test_reads_several_keyframes() -> None:
    body = b""
    for keyframe_id in ("k1", "k2"):
        body += struct.pack("<H", 2) + keyframe_id.encode() + struct.pack("<II", 1, 1)
        body += struct.pack("<H", 800) + bytes([200])
    images = read_depth(b"SJDEPTH1" + struct.pack("<I", 2) + body)
    assert sorted(images) == ["k1", "k2"]
    assert images["k2"].metres_at(0, 0) == 0.8


@pytest.mark.parametrize(
    "data, message",
    [
        (b"NOTDEPTH" + struct.pack("<I", 0), "not an SJDEPTH1"),
        (PHONE_BYTES[:-1], "truncated"),
        (PHONE_BYTES + b"x", "trailing"),
    ],
)
def test_rejects_bad_files(data: bytes, message: str) -> None:
    with pytest.raises(DepthFormatError, match=message):
        read_depth(data)


def test_rejects_a_keyframe_twice() -> None:
    entry = struct.pack("<H", 2) + b"k1" + struct.pack("<II", 1, 1) + struct.pack("<H", 1) + b"\x01"
    with pytest.raises(DepthFormatError, match="twice"):
        read_depth(b"SJDEPTH1" + struct.pack("<I", 2) + entry + entry)
