"""Download kept video segments. Built to run on the founder's Windows PC.

yt-dlp fetches only the requested time range of each video (it drives ffmpeg
to cut the stream), video only, up to a maximum height. Every finished clip is
checksummed and written to an append-only ledger, so a rerun skips what is
done and retries what failed.

Segments come from Gemini screening when it exists. Before screening, a
capped head of each kept video stands in (`origin="head"`).
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from sajao_dataset.manifest import SourceRecord
from sajao_dataset.prefilter import Decision
from sajao_dataset.youtube import rank


class Segment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    video_id: str = Field(pattern=r"^[A-Za-z0-9_-]{11}$")
    start_s: float = Field(ge=0)
    end_s: float
    room_type: str | None = None
    origin: Literal["screening", "head"]

    @model_validator(mode="after")
    def _ordered(self) -> Segment:
        if self.end_s <= self.start_s:
            raise ValueError("end_s must be after start_s")
        return self

    @property
    def key(self) -> tuple[str, int, int]:
        return (self.video_id, int(self.start_s), int(self.end_s))


class ClipRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    video_id: str
    start_s: float
    end_s: float
    room_type: str | None
    origin: Literal["screening", "head"]
    status: Literal["ok", "failed"]
    path: str | None
    """Relative to the clips folder, with forward slashes on every OS."""
    sha256: str | None
    bytes: int | None
    max_height: int
    error: str | None
    at: datetime


def plan_head_segments(
    sources: Iterable[SourceRecord],
    decisions: Iterable[Decision],
    *,
    head_s: float,
    limit: int,
) -> list[Segment]:
    """One head segment per kept video, up to `limit` videos: the priority category
    first, then Creative Commons first (see `youtube.rank`)."""
    keep = {d.video_id for d in decisions if d.keep}
    kept = [s for s in sources if s.video_id in keep]
    kept.sort(key=rank)  # stable: manifest order within a rank
    segments = []
    for source in kept[:limit]:
        end = min(head_s, source.duration_s) if source.duration_s else head_s
        segments.append(Segment(video_id=source.video_id, start_s=0, end_s=end, origin="head"))
    return segments


def plan_screened_segments(
    segments: Iterable[Segment],
    sources: Iterable[SourceRecord],
    *,
    limit_videos: int,
) -> list[Segment]:
    """Screened room segments for up to `limit_videos` videos: Creative Commons
    videos first, then the priority category, then manifest order. Segments of
    videos missing from `sources` (unavailable, or not in this manifest) are
    dropped, as are segments that did not come from screening."""
    order = {
        s.video_id: (s.license != "creative_commons", *rank(s), i) for i, s in enumerate(sources)
    }
    by_video: dict[str, list[Segment]] = {}
    for segment in segments:
        if segment.origin == "screening" and segment.video_id in order:
            by_video.setdefault(segment.video_id, []).append(segment)
    chosen = sorted(by_video, key=lambda v: order[v])[:limit_videos]
    return [seg for v in chosen for seg in sorted(by_video[v], key=lambda g: g.start_s)]


def clip_relpath(segment: Segment) -> str:
    _, start, end = segment.key
    return f"{segment.video_id}/{start:05d}-{end:05d}.mp4"


def ytdlp_options(
    segment: Segment,
    tmp_stem: Path,
    *,
    max_height: int,
    cookies_from_browser: str | None = None,
    ffmpeg_location: str | None = None,
    proxy: str | None = None,
) -> dict[str, Any]:
    from yt_dlp.utils import download_range_func

    h = max_height
    options: dict[str, Any] = {
        # Video only: frames are all we need, and it halves the download.
        "format": f"bv*[height<={h}][ext=mp4]/bv*[height<={h}]/b[height<={h}]/bv*/b",
        "download_ranges": download_range_func(None, [(segment.start_s, segment.end_s)]),
        "outtmpl": {"default": f"{tmp_stem}.%(ext)s"},
        "postprocessors": [{"key": "FFmpegVideoRemuxer", "preferedformat": "mp4"}],
        "retries": 5,
        "fragment_retries": 5,
        "quiet": True,
        "noprogress": True,
        "noplaylist": True,
    }
    if cookies_from_browser:
        options["cookiesfrombrowser"] = (cookies_from_browser,)
    if ffmpeg_location:
        options["ffmpeg_location"] = ffmpeg_location
    if proxy:
        # yt-dlp also hands the proxy to ffmpeg for range downloads, so the page,
        # the player and the media all leave from the same (sticky) address.
        options["proxy"] = proxy
    return options


Fetch = Callable[[Segment, Path], Path]
"""Downloads a segment to files named `<tmp_stem>.*` and returns the finished file."""


def ytdlp_fetch(
    *,
    max_height: int,
    cookies_from_browser: str | None = None,
    ffmpeg_location: str | None = None,
    proxy: str | None = None,
) -> Fetch:
    def fetch(segment: Segment, tmp_stem: Path) -> Path:
        import yt_dlp

        options = ytdlp_options(
            segment,
            tmp_stem,
            max_height=max_height,
            cookies_from_browser=cookies_from_browser,
            ffmpeg_location=ffmpeg_location,
            proxy=proxy,
        )
        url = f"https://www.youtube.com/watch?v={segment.video_id}"
        with yt_dlp.YoutubeDL(options) as ydl:
            if ydl.download([url]) != 0:
                raise RuntimeError("yt-dlp reported a failed download")
        produced = tmp_stem.with_name(f"{tmp_stem.name}.mp4")
        if not produced.exists():
            raise RuntimeError("yt-dlp finished but produced no mp4")
        check_clip(produced, segment, ffprobe=_ffprobe(ffmpeg_location))
        return produced

    return fetch


MIN_COVERAGE = 0.8
"""A clip must cover at least this share of the requested range."""


def check_clip(path: Path, segment: Segment, *, ffprobe: str) -> float:
    """Reject empty or truncated clips; yt-dlp can report success on both."""
    result = subprocess.run(  # noqa: S603  fixed arguments, no shell
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-count_packets",
            "-show_entries",
            "format=duration:stream=nb_read_packets",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    info = json.loads(result.stdout or "{}")
    streams = info.get("streams") or [{}]
    duration = float(info.get("format", {}).get("duration") or 0)
    packets = int(streams[0].get("nb_read_packets") or 0)
    wanted = segment.end_s - segment.start_s
    if result.returncode != 0 or packets == 0 or duration < MIN_COVERAGE * wanted:
        raise RuntimeError(f"clip check failed: {duration:.1f}s of {wanted:.1f}s, {packets} frames")
    return duration


def _ffprobe(ffmpeg_location: str | None) -> str:
    if not ffmpeg_location:
        return "ffprobe"
    location = Path(ffmpeg_location)
    folder = location if location.is_dir() else location.parent
    for name in ("ffprobe.exe", "ffprobe"):
        if (folder / name).exists():
            return str(folder / name)
    return "ffprobe"


@dataclass
class Summary:
    downloaded: int = 0
    skipped: int = 0
    failed: int = 0
    bytes: int = 0
    stopped_at_cap: bool = False


_CREDENTIALS = re.compile(r"(://)[^/@\s:]+:[^/@\s]+@")


def redact(text: str, *secrets: str | None) -> str:
    """Remove proxy URLs and any `user:password@` from error text before it is stored."""
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[proxy]")
    return _CREDENTIALS.sub(r"\1***@", text)


def read_ledger(path: Path) -> list[ClipRecord]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [ClipRecord.model_validate_json(line) for line in f if line.strip()]


def download_all(
    segments: Iterable[Segment],
    *,
    clips_dir: Path,
    ledger_path: Path,
    fetch: Fetch,
    max_height: int,
    pause_s: float,
    max_bytes: int | None = None,
    used_bytes: Callable[[], int] | None = None,
    bytes_per_s: float = 0.0,
    secrets: tuple[str | None, ...] = (),
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> Summary:
    """Fetch each segment not already done.

    With `max_bytes`, no segment starts once the bytes used so far plus this
    segment's estimate (`bytes_per_s` times its length) would pass the cap.
    `used_bytes` reports what the run has really transferred (for example the
    container's received bytes); without it the clips' sizes are used.
    """
    done = {
        (r.video_id, int(r.start_s), int(r.end_s))
        for r in read_ledger(ledger_path)
        if r.status == "ok" and r.path and (clips_dir / r.path).exists()
    }
    summary = Summary()
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_dir = clips_dir / ".tmp"
    first = True
    for segment in segments:
        if segment.key in done:
            summary.skipped += 1
            continue
        if max_bytes is not None:
            used = max(summary.bytes, used_bytes() if used_bytes else 0)
            if used + (segment.end_s - segment.start_s) * bytes_per_s > max_bytes:
                summary.stopped_at_cap = True
                break
        if not first:
            sleep(pause_s)  # rate limit: one request burst per segment
        first = False
        relpath = clip_relpath(segment)
        target = clips_dir / relpath
        tmp_dir.mkdir(parents=True, exist_ok=True)
        tmp_stem = tmp_dir / relpath.replace("/", "_").removesuffix(".mp4")
        try:
            produced = fetch(segment, tmp_stem)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(produced, target)
            digest, size = _sha256(target)
            record = _record(segment, "ok", relpath, digest, size, max_height, None, now())
            summary.downloaded += 1
            summary.bytes += size
        except Exception as error:  # one bad video never stops the batch
            message = redact(str(error), *secrets)
            record = _record(segment, "failed", None, None, None, max_height, message, now())
            summary.failed += 1
        finally:
            for leftover in tmp_dir.glob(f"{tmp_stem.name}*"):
                leftover.unlink(missing_ok=True)
        with ledger_path.open("a", encoding="utf-8", newline="\n") as f:
            f.write(record.model_dump_json() + "\n")
    return summary


def _record(
    segment: Segment,
    status: Literal["ok", "failed"],
    path: str | None,
    sha256: str | None,
    size: int | None,
    max_height: int,
    error: str | None,
    at: datetime,
) -> ClipRecord:
    return ClipRecord(
        video_id=segment.video_id,
        start_s=segment.start_s,
        end_s=segment.end_s,
        room_type=segment.room_type,
        origin=segment.origin,
        status=status,
        path=path,
        sha256=sha256,
        bytes=size,
        max_height=max_height,
        error=error[:500] if error else None,
        at=at,
    )


def _sha256(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as f:
        while chunk := f.read(1 << 20):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size
