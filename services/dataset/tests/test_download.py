import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import HttpUrl, ValidationError

from sajao_dataset.download import (
    Segment,
    check_clip,
    clip_relpath,
    download_all,
    plan_head_segments,
    read_ledger,
    ytdlp_options,
)
from sajao_dataset.manifest import SourceRecord
from sajao_dataset.prefilter import Decision

NOW = datetime(2000, 1, 1, tzinfo=UTC)


def source(video_id: str, license: str, duration_s: int | None) -> SourceRecord:
    return SourceRecord.model_validate(
        {
            "video_id": video_id,
            "url": HttpUrl(f"https://www.youtube.com/watch?v={video_id}"),
            "title": "t",
            "channel": None,
            "channel_id": None,
            "duration_s": duration_s,
            "license": license,
            "license_evidence": "none",
            "query": "q",
            "query_set": "s",
            "found_by": "yt-dlp",
            "found_at": NOW,
        }
    )


def keep(video_id: str, ok: bool = True) -> Decision:
    return Decision(video_id=video_id, keep=ok, reason=None, field=None, matched=None)


def seg(video_id: str = "aaaaaaaaaaa", start: float = 0, end: float = 30) -> Segment:
    return Segment(video_id=video_id, start_s=start, end_s=end, origin="head")


def test_plan_takes_kept_videos_creative_commons_first_and_caps_the_head() -> None:
    sources = [
        source("unknown0000", "unknown", 900),
        source("dropped0000", "creative_commons", 900),
        source("ccshort0000", "creative_commons", 200),
        source("nodur000000", "unknown", None),
    ]
    decisions = [
        keep("unknown0000"),
        keep("dropped0000", ok=False),
        keep("ccshort0000"),
        keep("nodur000000"),
    ]

    plan = plan_head_segments(sources, decisions, head_s=600, limit=2)

    assert [(s.video_id, s.end_s) for s in plan] == [("ccshort0000", 200), ("unknown0000", 600)]


def test_segment_must_end_after_it_starts() -> None:
    with pytest.raises(ValidationError):
        Segment(video_id="aaaaaaaaaaa", start_s=10, end_s=10, origin="head")


def test_ytdlp_options_fetch_only_the_range_video_only() -> None:
    options = ytdlp_options(
        seg(start=12.5, end=40),
        Path("tmp/x"),
        max_height=720,
        cookies_from_browser="edge",
        ffmpeg_location="C:/ffmpeg/bin",
    )
    assert options["format"].startswith("bv*[height<=720]")
    ranges = list(options["download_ranges"]({}, None))
    assert ranges == [{"start_time": 12.5, "end_time": 40}]
    assert options["cookiesfrombrowser"] == ("edge",)
    assert options["ffmpeg_location"] == "C:/ffmpeg/bin"
    assert "cookiesfrombrowser" not in ytdlp_options(seg(), Path("x"), max_height=720)


def test_download_writes_checksummed_clips_resumes_and_retries_failures(tmp_path: Path) -> None:
    clips, ledger = tmp_path / "clips", tmp_path / "downloads.jsonl"
    calls: list[str] = []
    pauses: list[float] = []
    broken = {"bbbbbbbbbbb"}

    def fetch(segment: Segment, tmp_stem: Path) -> Path:
        calls.append(segment.video_id)
        if segment.video_id in broken:
            raise RuntimeError("HTTP Error 403")
        produced = tmp_stem.with_name(tmp_stem.name + ".mp4")
        produced.write_bytes(b"clip " + segment.video_id.encode())
        return produced

    segments = [seg("aaaaaaaaaaa"), seg("bbbbbbbbbbb")]
    first = download_all(
        segments,
        clips_dir=clips,
        ledger_path=ledger,
        fetch=fetch,
        max_height=1080,
        pause_s=5,
        sleep=pauses.append,
        now=lambda: NOW,
    )
    assert (first.downloaded, first.failed, first.skipped) == (1, 1, 0)
    assert pauses == [5]
    assert (clips / clip_relpath(segments[0])).read_bytes() == b"clip aaaaaaaaaaa"
    assert not list((clips / ".tmp").iterdir())

    ok, failed = read_ledger(ledger)
    assert ok.status == "ok" and ok.path == "aaaaaaaaaaa/00000-00030.mp4"
    assert ok.sha256 and len(ok.sha256) == 64 and ok.bytes == 16
    assert failed.status == "failed" and failed.error == "HTTP Error 403"

    broken.clear()
    second = download_all(
        segments,
        clips_dir=clips,
        ledger_path=ledger,
        fetch=fetch,
        max_height=1080,
        pause_s=5,
        sleep=pauses.append,
        now=lambda: NOW,
    )
    assert (second.downloaded, second.failed, second.skipped) == (1, 0, 1)
    assert calls == ["aaaaaaaaaaa", "bbbbbbbbbbb", "bbbbbbbbbbb"]


def test_a_deleted_clip_is_downloaded_again(tmp_path: Path) -> None:
    clips, ledger = tmp_path / "clips", tmp_path / "downloads.jsonl"

    def fetch(segment: Segment, tmp_stem: Path) -> Path:
        produced = tmp_stem.with_name(tmp_stem.name + ".mp4")
        produced.write_bytes(b"x")
        return produced

    kwargs = dict(clips_dir=clips, ledger_path=ledger, fetch=fetch, max_height=1080, pause_s=0)
    download_all([seg()], **kwargs)  # type: ignore[arg-type]
    (clips / clip_relpath(seg())).unlink()
    assert download_all([seg()], **kwargs).downloaded == 1  # type: ignore[arg-type]


needs_ffmpeg = pytest.mark.skipif(
    not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="ffmpeg not installed"
)


def make_clip(path: Path, seconds: float) -> Path:
    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    subprocess.run(  # noqa: S603  fixed test command
        [
            ffmpeg,
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=320x180:rate=10",
            "-t",
            str(seconds),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        check=True,
    )
    return path


@needs_ffmpeg
def test_check_clip_accepts_a_full_clip(tmp_path: Path) -> None:
    clip = make_clip(tmp_path / "ok.mp4", 20)
    assert check_clip(clip, seg(start=30, end=50), ffprobe="ffprobe") == pytest.approx(20, abs=0.5)


@needs_ffmpeg
def test_check_clip_rejects_truncated_and_empty_clips(tmp_path: Path) -> None:
    short = make_clip(tmp_path / "short.mp4", 5)
    with pytest.raises(RuntimeError, match="clip check failed"):
        check_clip(short, seg(start=30, end=50), ffprobe="ffprobe")
    empty = tmp_path / "empty.mp4"
    empty.write_bytes(b"\x00" * 262)  # what yt-dlp left behind on a failed seek
    with pytest.raises(RuntimeError, match="clip check failed"):
        check_clip(empty, seg(start=30, end=50), ffprobe="ffprobe")
