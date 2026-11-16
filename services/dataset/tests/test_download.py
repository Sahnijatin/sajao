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
    plan_screened_segments,
    read_ledger,
    redact,
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


PROXY = "http://user-sp1-country-in-session-abc:S3cretPass@gate.example.com:10001"


def test_ytdlp_options_route_through_the_proxy_only_when_given(tmp_path: Path) -> None:
    assert "proxy" not in ytdlp_options(seg(), tmp_path / "x", max_height=720)
    options = ytdlp_options(seg(), tmp_path / "x", max_height=720, proxy=PROXY)
    assert options["proxy"] == PROXY
    assert "external_downloader_args" not in options
    local = "http://127.0.0.1:8899"
    forwarded = ytdlp_options(
        seg(), tmp_path / "x", max_height=720, proxy=PROXY, ffmpeg_proxy=local
    )
    assert forwarded["external_downloader_args"] == {"ffmpeg_i": ["-http_proxy", local]}
    assert "height<=720" in options["format"]


def test_redact_removes_the_proxy_and_any_credentials() -> None:
    text = f"Unable to connect to proxy {PROXY}; also https://u:p@other.example/x"
    clean = redact(text, PROXY)
    assert "S3cretPass" not in clean and "user-sp1" not in clean
    assert ":p@" not in clean and "[proxy]" in clean and "https://***@other.example" in clean
    assert redact("no secrets here", None) == "no secrets here"


def test_failed_downloads_never_store_the_proxy(tmp_path: Path) -> None:
    def fetch(segment: Segment, tmp_stem: Path) -> Path:
        raise RuntimeError(f"ProxyError: {PROXY} refused")

    download_all(
        [seg()],
        clips_dir=tmp_path / "clips",
        ledger_path=tmp_path / "d.jsonl",
        fetch=fetch,
        max_height=720,
        pause_s=0,
        secrets=(PROXY,),
        sleep=lambda _: None,
    )
    stored = (tmp_path / "d.jsonl").read_text()
    assert "S3cretPass" not in stored and "user-sp1" not in stored


def test_download_stops_before_the_byte_cap(tmp_path: Path) -> None:
    used = [0]

    def fetch(segment: Segment, tmp_stem: Path) -> Path:
        used[0] += 400  # what the network really carried for this segment
        produced = tmp_stem.with_name(tmp_stem.name + ".mp4")
        produced.write_bytes(b"x" * 100)
        return produced

    segments = [seg(start=i * 100, end=i * 100 + 10) for i in range(5)]
    summary = download_all(
        segments,
        clips_dir=tmp_path / "clips",
        ledger_path=tmp_path / "d.jsonl",
        fetch=fetch,
        max_height=720,
        pause_s=0,
        max_bytes=1000,
        used_bytes=lambda: used[0],
        bytes_per_s=10,  # 100 bytes estimated per 10 s segment
        sleep=lambda _: None,
    )
    # 0+100, 400+100, 800+100 fit; 1200 used would not.
    assert summary.downloaded == 3
    assert summary.stopped_at_cap
    assert len(read_ledger(tmp_path / "d.jsonl")) == 3


def test_plan_screened_segments_takes_creative_commons_videos_first() -> None:
    sources = [
        source("aaaaaaaaaaa", "standard", 600).model_copy(update={"category": "empty_new_build"}),
        source("bbbbbbbbbbb", "creative_commons", 600),
        source("ccccccccccc", "standard", 600),
        source("ddddddddddd", "creative_commons", 600).model_copy(
            update={"category": "empty_new_build"}
        ),
    ]

    def screened(video_id: str, start: float) -> Segment:
        return Segment(
            video_id=video_id,
            start_s=start,
            end_s=start + 20,
            room_type="kitchen",
            origin="screening",
        )

    segments = [
        screened("aaaaaaaaaaa", 0),
        screened("bbbbbbbbbbb", 60),
        screened("bbbbbbbbbbb", 10),
        screened("ccccccccccc", 0),
        screened("ddddddddddd", 0),
        screened("eeeeeeeeeee", 0),  # not in the manifest (unavailable): dropped
        seg("ccccccccccc"),  # a head segment, not screened: dropped
    ]
    plan = plan_screened_segments(segments, sources, limit_videos=3)
    assert [(s.video_id, s.start_s) for s in plan] == [
        ("ddddddddddd", 0),  # Creative Commons and priority category
        ("bbbbbbbbbbb", 10),  # Creative Commons, segments in time order
        ("bbbbbbbbbbb", 60),
        ("aaaaaaaaaaa", 0),  # standard license, priority category
    ]


def test_plan_screened_segments_caps_seconds_per_video() -> None:
    sources = [source("aaaaaaaaaaa", "creative_commons", 600)]
    segments = [
        Segment(video_id="aaaaaaaaaaa", start_s=start, end_s=start + 50, origin="screening")
        for start in (0, 100, 200)
    ]
    plan = plan_screened_segments(segments, sources, limit_videos=1, max_s_per_video=120)
    assert [(s.start_s, s.end_s) for s in plan] == [(0, 50), (100, 150), (200, 220)]
