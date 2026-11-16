import struct

from sajao_workers.capture_depth import read_depth_container

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
    image = read_depth_container(PHONE_BYTES)["k1"]
    assert image.millimetres.tolist() == [[1500, 0]]
    assert image.confidence.tolist() == [[255, 0]]
    assert image.confident_metres().tolist() == [[1.5, 0.0]]
