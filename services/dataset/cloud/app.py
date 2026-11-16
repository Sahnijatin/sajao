"""Modal job: download screened room segments through the residential proxy, then
sample frames. Replaces the Windows PC for the download and frames stages.

YouTube blocks downloads from cloud addresses, so yt-dlp (and the ffmpeg it
drives) goes through the residential proxy in the Modal secret `dataset-proxy`
(`YTDLP_PROXY_URL`, a sticky India session). The URL is never printed, logged
or stored; error text is redacted before it reaches the ledger.

Every run has a GB cap. The job counts the bytes the container really receives
during downloads (all of it through the proxy) and starts no segment that would
pass the cap. Clips, frames and ledgers live on the `sajao-dataset` volume, so a
rerun skips what is done.

Inputs come from the cloud stages run beforehand (find, licenses, prefilter,
screen): `data/sources.jsonl`, `data/licenses.jsonl` and `data/segments.jsonl`.

    uv run --with 'modal[api-proxy-support]==1.6.4' modal run services/dataset/cloud/app.py \\
        --limit-videos 5 --max-gb 0.3 --max-minutes-per-video 2   # the 5-video check
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import modal

HERE = Path(__file__).parent
PACKAGE = HERE.parent
DATA = Path("/data")
APP_NAME = "sajao-dataset-cloud"

# 720p video only. YouTube's 720p video streams run at about 1.5 to 2.5 Mbps; the
# estimate uses the top of that range plus 20 percent for pages, player and retries.
MAX_HEIGHT = 720
BYTES_PER_S = 2.5e6 / 8 * 1.2
FORWARDER = "http://127.0.0.1:8899"
# Sticky sessions: one per port. On a bot check, rate limit or dead session, move to
# the next port at most this often per phase (India, then any non-datacenter exit).
INDIA_HOST = "in.decodo.com"
FALLBACK_HOST = "gate.decodo.com"
FIRST_PORT = 10001
MAX_ROTATIONS = 3
# A segment may receive at most this many times its estimate (and at least 4 MB)
# before its download is killed, so one segment can never run through the cap.
SEGMENT_BUDGET_FACTOR = 3
SEGMENT_MIN_BUDGET = 4_000_000
# After this many budget kills on one video, its remaining segments are skipped
# for the run: the video does not seek and every segment would waste a budget.
MAX_KILLS_PER_VIDEO = 2

volume = modal.Volume.from_name("sajao-dataset", create_if_missing=True)
image = (
    modal.Image.debian_slim(python_version="3.13")
    .apt_install("ffmpeg")
    .pip_install(
        "yt-dlp[default,deno]==2026.10.26",
        "pydantic==2.14.3",
        "httpx==0.28.1",
        "numpy==2.5.5",
        "opencv-python-headless==5.0.0.93",
        "pproxy==2.7.9",
    )
    .add_local_dir(
        PACKAGE,
        "/pkg",
        copy=True,
        ignore=["data", "tests", "cloud", "**/__pycache__", "**/*.pyc"],
    )
    .run_commands("pip install --no-deps /pkg")
)
app = modal.App(APP_NAME, image=image)


def received_bytes() -> int:
    """Bytes received on every network interface except loopback."""
    total = 0
    for line in Path("/proc/net/dev").read_text().splitlines()[2:]:
        name, _, fields = line.partition(":")
        if name.strip() != "lo":
            total += int(fields.split()[0])
    return total


def start_forwarder(proxy: str) -> Any:
    """A local, credential-free proxy for ffmpeg that forwards to the sticky proxy.

    ffmpeg cannot open HTTPS through an authenticated proxy, so it talks to this
    forwarder on localhost instead. Credentials go to pproxy as `host:port#user:pass`.
    """
    import subprocess
    import urllib.request
    from urllib.parse import unquote, urlsplit

    parts = urlsplit(proxy)
    remote = (
        f"http://{parts.hostname}:{parts.port}"
        f"#{unquote(parts.username or '')}:{unquote(parts.password or '')}"
    )
    process = subprocess.Popen(  # noqa: S603  fixed arguments, no shell
        ["pproxy", "-l", FORWARDER, "-r", remote],  # noqa: S607  installed in the image
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({"http": FORWARDER, "https": FORWARDER})
    )
    for _ in range(30):
        time.sleep(1)
        try:
            opener.open("https://ipinfo.io/json", timeout=10).read()
            return process
        except OSError:
            continue
    process.kill()
    raise RuntimeError("the local proxy forwarder did not start")


def exit_info(proxy: str) -> tuple[str, str | None]:
    """Country and network name of the proxy's exit address (a few KB through it)."""
    import httpx

    try:
        with httpx.Client(proxy=proxy, timeout=30) as client:
            info = client.get("https://ipinfo.io/json").json()
            return str(info.get("country", "unknown")), info.get("org")
    except Exception as error:
        return f"check failed ({type(error).__name__})", None


class Sessions:
    """Sticky proxy sessions: India first, then any non-datacenter exit.

    India sessions are in.decodo.com ports 10001 to 10010; each port is its own
    sticky session. On a dead session, a bot check or a rate limit the job moves to
    the next port, at most MAX_ROTATIONS times per phase. When India keeps failing,
    it falls back to the general endpoint on the same ports and accepts any country
    whose network does not look like a datacenter.
    """

    def __init__(self, proxy: str) -> None:
        from sajao_dataset.download import with_endpoint

        self.phases = [
            ("India", with_endpoint(proxy, INDIA_HOST, FIRST_PORT), "IN"),
            ("any country", with_endpoint(proxy, FALLBACK_HOST, FIRST_PORT), None),
        ]
        self.phase = 0
        self.rotations = 0
        self.proxy = self.phases[0][1]
        self.country: str | None = None
        self.log: list[dict[str, Any]] = []
        self.seen: list[str] = [proxy]
        self.forwarder: Any = None

    def _acceptable(self, country: str, org: str | None) -> bool:
        from sajao_dataset.download import looks_like_datacenter

        wanted = self.phases[self.phase][2]
        if country.startswith("check failed") or looks_like_datacenter(org):
            return False
        return wanted is None or country == wanted

    def connect(self) -> bool:
        """Find a usable session from the current one onwards. False if none is left."""
        from sajao_dataset.download import next_session

        while True:
            country, org = exit_info(self.proxy)
            ok = self._acceptable(country, org)
            self.log.append({"phase": self.phases[self.phase][0], "country": country, "usable": ok})
            if ok:
                self.country = country
                if self.forwarder is not None:
                    self.forwarder.kill()
                self.forwarder = start_forwarder(self.proxy)
                return True
            if not self.advance(next_session):
                return False

    def advance(self, next_session: Any) -> bool:
        """Move to the next port, or to the fallback phase when this one is used up."""
        if self.rotations < MAX_ROTATIONS:
            self.rotations += 1
            self.proxy = next_session(self.proxy)
        elif self.phase + 1 < len(self.phases):
            self.phase += 1
            self.rotations = 0
            self.proxy = self.phases[self.phase][1]
        else:
            return False
        self.seen.append(self.proxy)
        return True

    def rotate(self) -> bool:
        from sajao_dataset.download import next_session

        return self.advance(next_session) and self.connect()

    def close(self) -> None:
        if self.forwarder is not None:
            self.forwarder.kill()


@app.function(
    secrets=[modal.Secret.from_name("dataset-proxy")],
    volumes={str(DATA): volume},
    cpu=2,
    memory=4096,
    timeout=6 * 3600,
)
def download_and_sample(
    segments: list[dict[str, Any]],
    max_gb: float,
    pause_s: float = 5.0,
    dry_run: bool = False,
) -> dict[str, Any]:
    from datetime import UTC, datetime

    from sajao_dataset.download import (
        BudgetExceededError,
        Segment,
        check_clip,
        download_all,
        is_blocked,
        read_ledger,
        redact,
        run_with_byte_budget,
        ytdlp_cli_args,
    )
    from sajao_dataset.frames import fetch_yunet, sample_all, yunet_faces

    run_started = datetime.now(UTC)
    started = time.time()
    start_rx = received_bytes()
    cap = int(max_gb * 1e9)

    def used() -> int:
        return received_bytes() - start_rx

    sessions = Sessions(os.environ["YTDLP_PROXY_URL"])
    if not sessions.connect() or dry_run:
        sessions.close()
        if dry_run:
            return {"dry_run": True, "sessions": sessions.log, "proxy_bytes_received": used()}
        return {
            "refused": "no usable proxy session",
            "sessions": sessions.log,
            "proxy_bytes_received": used(),
        }

    kills: dict[str, int] = {}

    def fetch_once(segment: Segment, tmp_stem: Path) -> Path:
        if kills.get(segment.video_id, 0) >= MAX_KILLS_PER_VIDEO:
            raise RuntimeError("skipped: this video went over its budget twice in this run")
        estimate = (segment.end_s - segment.start_s) * BYTES_PER_S
        budget = int(min(max(SEGMENT_MIN_BUDGET, SEGMENT_BUDGET_FACTOR * estimate), cap - used()))
        if budget <= 0:
            raise BudgetExceededError("the run cap is used up")
        env = dict(os.environ, HTTPS_PROXY=sessions.proxy, HTTP_PROXY=sessions.proxy)
        try:
            code, err = run_with_byte_budget(
                ytdlp_cli_args(segment, tmp_stem, max_height=MAX_HEIGHT, ffmpeg_proxy=FORWARDER),
                budget_bytes=budget,
                used_bytes=used,
                env=env,
            )
        except BudgetExceededError:
            kills[segment.video_id] = kills.get(segment.video_id, 0) + 1
            raise
        produced = tmp_stem.with_name(f"{tmp_stem.name}.mp4")
        if code != 0 or not produced.exists():
            lines = [line for line in err.splitlines() if "ERROR" in line] or [err[-300:]]
            raise RuntimeError(redact(lines[-1], *sessions.seen))
        check_clip(produced, segment, ffprobe="ffprobe")
        return produced

    def fetch(segment: Segment, tmp_stem: Path) -> Path:
        for attempt in (1, 2):
            try:
                return fetch_once(segment, tmp_stem)
            except Exception as error:
                if attempt == 2 or not is_blocked(str(error)) or not sessions.rotate():
                    raise
        raise AssertionError("unreachable")

    try:
        summary = download_all(
            [Segment.model_validate(s) for s in segments],
            clips_dir=DATA / "clips",
            ledger_path=DATA / "downloads.jsonl",
            fetch=fetch,
            max_height=MAX_HEIGHT,
            pause_s=pause_s,
            max_bytes=cap,
            used_bytes=used,
            bytes_per_s=BYTES_PER_S,
            secrets=tuple(sessions.seen),
            exit_country=lambda: sessions.country,
        )
    finally:
        sessions.close()
    proxy_bytes = used()
    volume.commit()
    download_s = time.time() - started

    # Frames: no proxy needed (YuNet comes from GitHub, clips are on the volume).
    frames = sample_all(
        read_ledger(DATA / "downloads.jsonl"),
        clips_dir=DATA / "clips",
        frames_dir=DATA / "frames",
        frames_ledger=DATA / "frames.jsonl",
        done_ledger=DATA / "frames_done.jsonl",
        faces=yunet_faces(fetch_yunet(DATA / "models")),
        ffmpeg="ffmpeg",
    )
    volume.commit()

    rows = [r for r in read_ledger(DATA / "downloads.jsonl") if r.at >= run_started]
    return {
        "sessions": sessions.log,
        "proxy_bytes_received": proxy_bytes,
        "clip_bytes": summary.bytes,
        "downloaded": summary.downloaded,
        "already_done": summary.skipped,
        "failed": summary.failed,
        "stopped_at_cap": summary.stopped_at_cap,
        "download_seconds": round(download_s),
        "clips": [
            {
                "video": r.video_id,
                "start_s": r.start_s,
                "status": r.status,
                "exit_country": r.exit_country,
                "mb": round((r.proxy_bytes or 0) / 1e6, 1),
                "error": (r.error or "")[:120] or None,
            }
            for r in rows
        ],
        "frames": {
            "clips": frames.clips,
            "candidates": frames.candidates,
            "kept": frames.kept,
            "faces_blurred": frames.faces_blurred,
            "dropped": dict(frames.dropped),
        },
    }


@app.local_entrypoint()
def main(
    limit_videos: int = 5,
    max_gb: float = 0.5,
    max_minutes_per_video: float = 0.0,
    data: str = "services/dataset/data",
    pause_s: float = 5.0,
    dry_run: bool = False,
) -> None:
    from sajao_dataset.download import Segment, plan_screened_segments
    from sajao_dataset.licenses import apply_licenses, read_licenses
    from sajao_dataset.manifest import read_manifest

    root = Path(data)
    sources = apply_licenses(
        read_manifest(root / "sources.jsonl"), read_licenses(root / "licenses.jsonl")
    )
    with (root / "segments.jsonl").open(encoding="utf-8") as f:
        screened = [Segment.model_validate_json(line) for line in f if line.strip()]
    plan = plan_screened_segments(
        screened,
        sources,
        limit_videos=limit_videos,
        max_s_per_video=max_minutes_per_video * 60 or None,
    )
    videos = sorted({s.video_id for s in plan})
    minutes = sum(s.end_s - s.start_s for s in plan) / 60
    print(f"{len(plan)} segments from {len(videos)} videos, {minutes:.1f} min, cap {max_gb} GB")

    result = download_and_sample.remote(
        [s.model_dump() for s in plan],
        max_gb=max_gb,
        pause_s=pause_s,
        dry_run=dry_run,
    )
    result["videos"] = videos
    result["segment_minutes"] = round(minutes, 1)
    print(json.dumps(result, indent=1))
    with (root / "cloud_runs.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps({"at": time.time(), **result}) + "\n")
