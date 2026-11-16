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
        --limit-videos 5 --max-gb 0.5
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


def proxy_country(proxy: str) -> str:
    """Country of the proxy's exit address (a few KB through the proxy)."""
    import httpx

    try:
        with httpx.Client(proxy=proxy, timeout=30) as client:
            return str(client.get("https://ipinfo.io/json").json().get("country", "unknown"))
    except Exception as error:
        return f"check failed ({type(error).__name__})"


@app.function(
    secrets=[modal.Secret.from_name("dataset-proxy")],
    volumes={str(DATA): volume},
    cpu=2,
    memory=4096,
    timeout=6 * 3600,
)
def download_and_sample(
    segments: list[dict[str, Any]], max_gb: float, pause_s: float = 5.0
) -> dict[str, Any]:
    from sajao_dataset.download import Segment, download_all, read_ledger, ytdlp_fetch
    from sajao_dataset.frames import fetch_yunet, sample_all, yunet_faces

    proxy = os.environ["YTDLP_PROXY_URL"]
    started = time.time()
    start_rx = received_bytes()
    country = proxy_country(proxy)

    summary = download_all(
        [Segment.model_validate(s) for s in segments],
        clips_dir=DATA / "clips",
        ledger_path=DATA / "downloads.jsonl",
        fetch=ytdlp_fetch(max_height=MAX_HEIGHT, proxy=proxy),
        max_height=MAX_HEIGHT,
        pause_s=pause_s,
        max_bytes=int(max_gb * 1e9),
        used_bytes=lambda: received_bytes() - start_rx,
        bytes_per_s=BYTES_PER_S,
        secrets=(proxy,),
    )
    proxy_bytes = received_bytes() - start_rx
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

    wanted = {(s["video_id"], int(s["start_s"]), int(s["end_s"])) for s in segments}
    rows = [
        r
        for r in read_ledger(DATA / "downloads.jsonl")
        if (r.video_id, int(r.start_s), int(r.end_s)) in wanted
    ]
    return {
        "proxy_country": country,
        "proxy_bytes_received": proxy_bytes,
        "clip_bytes": summary.bytes,
        "downloaded": summary.downloaded,
        "already_done": summary.skipped,
        "failed": summary.failed,
        "stopped_at_cap": summary.stopped_at_cap,
        "download_seconds": round(download_s),
        "frames": {
            "clips": frames.clips,
            "candidates": frames.candidates,
            "kept": frames.kept,
            "faces_blurred": frames.faces_blurred,
            "dropped": dict(frames.dropped),
        },
        "errors": sorted({(r.error or "")[:200] for r in rows if r.status == "failed"}),
    }


@app.local_entrypoint()
def main(
    limit_videos: int = 5,
    max_gb: float = 0.5,
    data: str = "services/dataset/data",
    pause_s: float = 5.0,
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
    plan = plan_screened_segments(screened, sources, limit_videos=limit_videos)
    videos = sorted({s.video_id for s in plan})
    minutes = sum(s.end_s - s.start_s for s in plan) / 60
    print(f"{len(plan)} segments from {len(videos)} videos, {minutes:.1f} min, cap {max_gb} GB")

    result = download_and_sample.remote(
        [s.model_dump() for s in plan], max_gb=max_gb, pause_s=pause_s
    )
    result["videos"] = videos
    result["segment_minutes"] = round(minutes, 1)
    print(json.dumps(result, indent=1))
    with (root / "cloud_runs.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps({"at": time.time(), **result}) + "\n")
