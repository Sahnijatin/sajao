import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

from sajao_dataset.download import ClipRecord
from sajao_dataset.frames import (
    YUNET_SHA256,
    FrameRecord,
    blur_faces,
    dhash,
    fetch_yunet,
    hamming,
    sample_all,
    select_filter,
    sharpness,
)

FFMPEG = shutil.which("ffmpeg")
needs_ffmpeg = pytest.mark.skipif(FFMPEG is None, reason="ffmpeg not installed")


def ffmpeg(*args: str) -> None:
    subprocess.run([FFMPEG or "ffmpeg", "-v", "error", "-y", *args], check=True)  # noqa: S603


PAN = (
    "mandelbrot=s=3200x900:rate=10:start_scale=0.3:end_scale=0.3,"
    "trim=end_frame=1,loop=loop=200:size=1:start=0,setpts=N/10/TB"
)


def make_fixture(folder: Path) -> Path:
    """6 s sharp pan, 4 s blurred pan, 6 s still shot of another view."""
    enc = ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "10"]
    ffmpeg(
        "-f",
        "lavfi",
        "-i",
        PAN,
        "-vf",
        "crop=640:360:x='t*100':y=0",
        "-t",
        "6",
        *enc,
        str(folder / "a.mp4"),
    )
    ffmpeg(
        "-f",
        "lavfi",
        "-i",
        PAN,
        "-vf",
        "crop=640:360:x='900+t*100':y=0,boxblur=12:2",
        "-t",
        "4",
        *enc,
        str(folder / "b.mp4"),
    )
    ffmpeg(
        "-f",
        "lavfi",
        "-i",
        PAN,
        "-vf",
        "crop=640:360:x=1300:y=0",
        "-t",
        "6",
        *enc,
        str(folder / "c.mp4"),
    )
    out = folder / "clip.mp4"
    ffmpeg(
        "-i",
        str(folder / "a.mp4"),
        "-i",
        str(folder / "b.mp4"),
        "-i",
        str(folder / "c.mp4"),
        "-filter_complex",
        "[0:v][1:v][2:v]concat=n=3:v=1[v]",
        "-map",
        "[v]",
        *enc,
        str(out),
    )
    return out


def clip_record(path: str, sha: str = "a" * 64, start_s: float = 100) -> ClipRecord:
    return ClipRecord(
        video_id="aaaaaaaaaaa",
        start_s=start_s,
        end_s=start_s + 16,
        room_type="living_room",
        origin="screening",
        status="ok",
        path=path,
        sha256=sha,
        bytes=1,
        max_height=1080,
        error=None,
        at=datetime(2000, 1, 1, tzinfo=UTC),
    )


@needs_ffmpeg
def test_sampling_keeps_sharp_distinct_frames_and_drops_blur_and_duplicates(tmp_path: Path) -> None:
    clips = tmp_path / "clips"
    (clips / "aaaaaaaaaaa").mkdir(parents=True)
    make_fixture(tmp_path).rename(clips / "aaaaaaaaaaa" / "00100-00116.mp4")
    frames, ledger, done = tmp_path / "frames", tmp_path / "frames.jsonl", tmp_path / "done.jsonl"
    face_calls: list[tuple[int, ...]] = []

    def faces(image: np.ndarray) -> list[tuple[int, int, int, int]]:
        face_calls.append(image.shape)
        return [(10, 10, 40, 40)]

    clip = clip_record("aaaaaaaaaaa/00100-00116.mp4")
    summary = sample_all(
        [clip],
        clips_dir=clips,
        frames_dir=frames,
        frames_ledger=ledger,
        done_ledger=done,
        faces=faces,
    )

    records = [FrameRecord.model_validate_json(x) for x in ledger.read_text().splitlines()]
    times = [r.t_s for r in records]
    assert times == [100.0, 102.0, 104.0, 110.0]  # pan, then the first still frame
    assert summary.dropped["blur"] == 2
    assert summary.dropped["near_duplicate"] == 2
    assert all(r.room_type == "living_room" and r.faces_blurred == 1 for r in records)
    assert len(face_calls) == len(records)  # faces are checked only on frames that are kept
    assert all((frames / r.path).is_file() for r in records)
    assert not any((frames / ".tmp").iterdir())  # unblurred candidates are gone

    again = sample_all(
        [clip],
        clips_dir=clips,
        frames_dir=frames,
        frames_ledger=ledger,
        done_ledger=done,
        faces=faces,
    )
    assert (again.clips, again.skipped) == (0, 1)


@needs_ffmpeg
def test_a_second_clip_of_the_same_view_counts_as_a_repeat(tmp_path: Path) -> None:
    clips = tmp_path / "clips"
    (clips / "aaaaaaaaaaa").mkdir(parents=True)
    still = clips / "aaaaaaaaaaa" / "still.mp4"
    ffmpeg(
        "-f",
        "lavfi",
        "-i",
        PAN,
        "-vf",
        "crop=640:360:x=1300:y=0",
        "-t",
        "2",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(still),
    )
    shutil.copy(still, clips / "aaaaaaaaaaa" / "still2.mp4")
    kwargs = dict(
        clips_dir=clips,
        frames_dir=tmp_path / "f",
        frames_ledger=tmp_path / "l.jsonl",
        done_ledger=tmp_path / "d.jsonl",
        faces=lambda image: [],
    )
    first = sample_all([clip_record("aaaaaaaaaaa/still.mp4", "1" * 64)], **kwargs)  # type: ignore[arg-type]
    second = sample_all([clip_record("aaaaaaaaaaa/still2.mp4", "2" * 64, 200)], **kwargs)  # type: ignore[arg-type]
    assert first.kept == 1
    assert (second.kept, second.dropped["repeat"]) == (0, 1)


def test_select_filter_combines_first_frame_scene_changes_and_interval() -> None:
    f = select_filter(scene=0.2, interval_s=2.0)
    assert "eq(n\\,0)" in f and "gt(scene\\,0.2)" in f and "floor(t/2.0)" in f
    assert f.endswith("showinfo")


def test_sharpness_separates_detail_from_blur() -> None:
    rng = np.random.default_rng(0)
    detail = rng.integers(0, 255, (360, 640, 3), dtype=np.uint8)
    flat = np.full((360, 640, 3), 128, dtype=np.uint8)
    assert sharpness(detail) > 1000 > 1 > sharpness(flat)


def test_dhash_is_stable_under_small_changes_and_differs_for_other_views() -> None:
    rng = np.random.default_rng(1)
    a = rng.integers(0, 255, (360, 640, 3), dtype=np.uint8)
    noisy = np.clip(a.astype(np.int16) + rng.integers(-3, 4, a.shape), 0, 255).astype(np.uint8)
    b = rng.integers(0, 255, (360, 640, 3), dtype=np.uint8)
    assert hamming(dhash(a), dhash(noisy)) <= 12 < hamming(dhash(a), dhash(b))


def test_blur_faces_changes_only_the_padded_face_region() -> None:
    rng = np.random.default_rng(2)
    image = rng.integers(0, 255, (200, 200, 3), dtype=np.uint8)
    out, count = blur_faces(image, [(80, 80, 40, 40), (500, 500, 10, 10)])
    assert count == 1
    assert np.array_equal(out[:60], image[:60])
    assert not np.array_equal(out[80:120, 80:120], image[80:120, 80:120])


def test_fetch_yunet_verifies_the_checksum(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="pinned checksum"):
        fetch_yunet(tmp_path, download=lambda url: b"tampered")
    assert len(YUNET_SHA256) == 64
