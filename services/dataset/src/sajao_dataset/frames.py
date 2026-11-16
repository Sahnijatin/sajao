"""Sample frames from downloaded clips, drop blur and near-duplicates, blur faces.

Per clip:

1. One ffmpeg pass selects the first frame, every scene change and one frame
   per interval (home tours are mostly slow pans with few hard cuts), and logs
   each selected frame's timestamp with `showinfo`.
2. In time order, each candidate is dropped if it is blurred (variance of the
   Laplacian), nearly identical to the last kept frame (mean difference of
   16x16 colour thumbnails) or a repeat of any frame already kept from the same
   video (64-bit difference hash).
3. Faces are blurred before a frame is written to the dataset. Unblurred
   candidates live only in a temporary folder that is always cleaned up.

The selection expression, showinfo timestamps and thumbnail dedup follow ideas
from bradautomates/claude-video (MIT), reimplemented here.

Every threshold is pinned; changing one means a new SAMPLER_VERSION.
"""

from __future__ import annotations

import hashlib
import itertools
import re
import shutil
import subprocess
import urllib.request
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import cv2
import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict

from sajao_dataset.download import ClipRecord

SAMPLER_VERSION = "frames-v1"
SCENE_THRESHOLD = 0.20
INTERVAL_S = 2.0
MAX_WIDTH = 1280
JPEG_QUALITY = 92
BLUR_WIDTH = 640
BLUR_MIN = 60.0
"""Variance of the Laplacian on a 640 px wide grey copy; below this a frame is blurred."""
THUMB = 16
THUMB_DELTA_MAX = 3.0
"""Mean absolute difference (0 to 255) of 16x16 colour thumbnails; at or below is a duplicate."""
DHASH_SIZE = 16
DHASH_DISTANCE_MAX = 12
"""Hamming distance of 256-bit difference hashes; at or below repeats a kept frame.
On a slow synthetic pan, frames 2 s apart differ by 35 or more."""
FACE_SCORE_MIN = 0.6
FACE_MARGIN = 0.25

Image = NDArray[np.uint8]
Box = tuple[int, int, int, int]
FaceFinder = Callable[[Image], list[Box]]


class FrameRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    video_id: str
    clip_path: str
    clip_sha256: str
    t_s: float
    """Time in the source video, in seconds."""
    room_type: str | None
    path: str
    """Relative to the frames folder, with forward slashes."""
    sha256: str
    width: int
    height: int
    sharpness: float
    faces_blurred: int
    dhash: str
    sampler: str = SAMPLER_VERSION


class ClipDone(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    clip_sha256: str
    video_id: str
    candidates: int
    kept: int
    dropped: dict[str, int]
    sampler: str = SAMPLER_VERSION
    at: datetime


@dataclass(frozen=True)
class Candidate:
    t_s: float
    path: Path


# Selection ---------------------------------------------------------------------------

_PTS = re.compile(r"pts_time:\s*([-0-9.eE+]+)")


def select_filter(*, scene: float = SCENE_THRESHOLD, interval_s: float = INTERVAL_S) -> str:
    select = (
        f"eq(n\\,0)+gt(scene\\,{scene})"
        f"+gt(floor(t/{interval_s})\\,floor(prev_selected_t/{interval_s}))"
    )
    return f"select='{select}',scale='min({MAX_WIDTH}\\,iw)':-2,showinfo"


def extract_candidates(clip: Path, out_dir: Path, *, ffmpeg: str = "ffmpeg") -> list[Candidate]:
    out_dir.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(  # noqa: S603  fixed arguments, no shell
        [
            ffmpeg,
            "-hide_banner",
            "-nostats",
            "-i",
            str(clip),
            "-vf",
            select_filter(),
            "-fps_mode",
            "passthrough",
            "-q:v",
            "2",
            str(out_dir / "c_%06d.jpg"),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=3600,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg frame selection failed: {result.stderr[-500:]}")
    files = sorted(out_dir.glob("c_*.jpg"))
    stamps = [float(m) for m in _PTS.findall(result.stderr)]
    # Refuse to guess: every written frame needs its own timestamp.
    if len(stamps) < len(files) or any(b < a for a, b in itertools.pairwise(stamps)):
        raise RuntimeError("ffmpeg did not log a timestamp for every selected frame")
    return [Candidate(t_s=stamps[i], path=path) for i, path in enumerate(files)]


# Filters -----------------------------------------------------------------------------


def sharpness(image: Image) -> float:
    grey = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    h, w = grey.shape
    if w > BLUR_WIDTH:
        grey = cv2.resize(
            grey, (BLUR_WIDTH, round(h * BLUR_WIDTH / w)), interpolation=cv2.INTER_AREA
        )
    return float(cv2.Laplacian(grey, cv2.CV_64F).var())


def thumbnail(image: Image) -> NDArray[np.int16]:
    return cv2.resize(image, (THUMB, THUMB), interpolation=cv2.INTER_AREA).astype(np.int16)


def thumb_delta(a: NDArray[np.int16], b: NDArray[np.int16]) -> float:
    return float(np.abs(a - b).mean())


def dhash(image: Image) -> int:
    grey = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    small = cv2.resize(grey, (DHASH_SIZE + 1, DHASH_SIZE), interpolation=cv2.INTER_AREA)
    bits = (small[:, 1:] > small[:, :-1]).flatten()
    return int("".join("1" if b else "0" for b in bits), 2)


def hamming(a: int, b: int) -> int:
    return (a ^ b).bit_count()


def blur_faces(image: Image, boxes: Iterable[Box]) -> tuple[Image, int]:
    out = image.copy()
    h, w = out.shape[:2]
    count = 0
    for x, y, bw, bh in boxes:
        mx, my = round(bw * FACE_MARGIN), round(bh * FACE_MARGIN)
        x0, y0 = max(0, x - mx), max(0, y - my)
        x1, y1 = min(w, x + bw + mx), min(h, y + bh + my)
        if x1 <= x0 or y1 <= y0:
            continue
        region = out[y0:y1, x0:x1]
        k = max(3, (max(x1 - x0, y1 - y0) // 3) | 1)  # odd kernel, strong enough to hide identity
        out[y0:y1, x0:x1] = cv2.GaussianBlur(region, (k, k), 0)
        count += 1
    return out, count


# Face detector -----------------------------------------------------------------------

YUNET_URLS = (
    "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
    "https://huggingface.co/opencv/face_detection_yunet/resolve/main/face_detection_yunet_2023mar.onnx",
)
YUNET_SHA256 = "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"


def fetch_yunet(cache_dir: Path, download: Callable[[str], bytes] | None = None) -> Path:
    """Return the pinned YuNet model, downloading and verifying it once."""
    target = cache_dir / "face_detection_yunet_2023mar.onnx"
    if target.exists() and _sha256_bytes(target.read_bytes()) == YUNET_SHA256:
        return target
    get = download or _http_get
    for url in YUNET_URLS:
        try:
            data = get(url)
        except OSError:
            continue
        if _sha256_bytes(data) == YUNET_SHA256:
            cache_dir.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            return target
    raise RuntimeError("could not fetch the face model with the pinned checksum")


def _http_get(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=60) as response:  # noqa: S310  pinned https URLs
        data: bytes = response.read()
        return data


def yunet_faces(model: Path) -> FaceFinder:
    detector = cv2.FaceDetectorYN.create(str(model), "", (320, 320), FACE_SCORE_MIN)

    def find(image: Image) -> list[Box]:
        h, w = image.shape[:2]
        detector.setInputSize((w, h))
        _, faces = detector.detect(image)
        if faces is None:
            return []
        return [(int(f[0]), int(f[1]), int(f[2]), int(f[3])) for f in faces]

    return find


# Pipeline ----------------------------------------------------------------------------


@dataclass
class Summary:
    clips: int = 0
    skipped: int = 0
    candidates: int = 0
    kept: int = 0
    faces_blurred: int = 0
    dropped: Counter[str] = field(default_factory=Counter)


def sample_clip(
    clip: ClipRecord,
    *,
    clips_dir: Path,
    frames_dir: Path,
    faces: FaceFinder,
    known_hashes: list[int],
    ffmpeg: str = "ffmpeg",
) -> tuple[list[FrameRecord], ClipDone]:
    """Sample one clip. `known_hashes` holds hashes kept earlier for the same video
    and is extended with this clip's kept frames."""
    if not (clip.path and clip.sha256):
        raise ValueError("only clips downloaded with status ok can be sampled")
    source = clips_dir / clip.path
    tmp = frames_dir / ".tmp" / clip.sha256[:16]
    shutil.rmtree(tmp, ignore_errors=True)
    records: list[FrameRecord] = []
    dropped: Counter[str] = Counter()
    try:
        candidates = extract_candidates(source, tmp, ffmpeg=ffmpeg)
        last_thumb: NDArray[np.int16] | None = None
        for cand in candidates:
            loaded = cv2.imread(str(cand.path), cv2.IMREAD_COLOR)
            if loaded is None:
                dropped["unreadable"] += 1
                continue
            image: Image = np.asarray(loaded, dtype=np.uint8)
            sharp = sharpness(image)
            if sharp < BLUR_MIN:
                dropped["blur"] += 1
                continue
            thumb = thumbnail(image)
            if last_thumb is not None and thumb_delta(thumb, last_thumb) <= THUMB_DELTA_MAX:
                dropped["near_duplicate"] += 1
                continue
            h = dhash(image)
            if any(hamming(h, k) <= DHASH_DISTANCE_MAX for k in known_hashes):
                dropped["repeat"] += 1
                continue
            last_thumb = thumb
            known_hashes.append(h)
            safe, n_faces = blur_faces(image, faces(image))
            t_s = round(clip.start_s + cand.t_s, 3)
            rel = f"{clip.video_id}/{round(t_s * 1000):09d}.jpg"
            target = frames_dir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            ok, encoded = cv2.imencode(".jpg", safe, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
            if not ok:
                dropped["unwritable"] += 1
                continue
            data = encoded.tobytes()
            target.write_bytes(data)
            records.append(
                FrameRecord(
                    video_id=clip.video_id,
                    clip_path=clip.path,
                    clip_sha256=clip.sha256,
                    t_s=t_s,
                    room_type=clip.room_type,
                    path=rel,
                    sha256=_sha256_bytes(data),
                    width=int(safe.shape[1]),
                    height=int(safe.shape[0]),
                    sharpness=round(sharp, 2),
                    faces_blurred=n_faces,
                    dhash=f"{h:064x}",
                )
            )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)  # unblurred candidates never persist
    done = ClipDone(
        clip_sha256=clip.sha256,
        video_id=clip.video_id,
        candidates=len(candidates),
        kept=len(records),
        dropped=dict(dropped),
        at=datetime.now(UTC),
    )
    return records, done


def sample_all(
    clips: Iterable[ClipRecord],
    *,
    clips_dir: Path,
    frames_dir: Path,
    frames_ledger: Path,
    done_ledger: Path,
    faces: FaceFinder,
    ffmpeg: str = "ffmpeg",
) -> Summary:
    done = {d.clip_sha256 for d in _read(done_ledger, ClipDone)}
    hashes: dict[str, list[int]] = {}
    for record in _read(frames_ledger, FrameRecord):
        hashes.setdefault(record.video_id, []).append(int(record.dhash, 16))
    summary = Summary()
    for clip in clips:
        if clip.status != "ok" or not clip.sha256:
            continue
        if clip.sha256 in done:
            summary.skipped += 1
            continue
        records, clip_done = sample_clip(
            clip,
            clips_dir=clips_dir,
            frames_dir=frames_dir,
            faces=faces,
            known_hashes=hashes.setdefault(clip.video_id, []),
            ffmpeg=ffmpeg,
        )
        _append(frames_ledger, records)
        _append(done_ledger, [clip_done])  # written last: a crash reprocesses the clip
        done.add(clip.sha256)
        summary.clips += 1
        summary.candidates += clip_done.candidates
        summary.kept += clip_done.kept
        summary.faces_blurred += sum(r.faces_blurred for r in records)
        summary.dropped.update(clip_done.dropped)
    return summary


def _read[M: BaseModel](path: Path, model: type[M]) -> list[M]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [model.model_validate_json(line) for line in f if line.strip()]


def _append(path: Path, rows: Iterable[BaseModel]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(row.model_dump_json() + "\n")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
