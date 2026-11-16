# Detector dataset pipeline

Builds a labelled set of real Indian rooms for the on-device detector. Every stage reads and writes a validated JSONL manifest under `data/` (never committed), so each stage is idempotent and resumes where it stopped.

| Stage | Command | Status |
| --- | --- | --- |
| 1. Find candidate videos | `find` | Ready |
| 1a. Record each video's license (YouTube Data API) | `licenses` | Ready |
| 1b. Drop builder and designer promos | `prefilter` | Ready |
| 2. Screen with Gemini on Vertex AI (keep or skip, room timestamps) | `screen` | Ready |
| 3. Download kept room segments (Modal, through the proxy; or a home PC) | `cloud/app.py`, `download` | Ready |
| 4. Sample frames, drop near-duplicates and blur, blur faces | `cloud/app.py`, `frames` | Ready |
| 5. Auto-label and hand-check | | Next |
| 6. Version the dataset on Modal | | Next |

## Use rules

- Every video's license is recorded. Creative Commons videos come first.
- The dataset is for internal training only and is never redistributed. Each record carries `use: internal_training_only`.
- Every source, tool and model is in `docs/24-third-party-register.md`, flagged for legal where needed.

## 1. Find candidate videos

```sh
uv run python -m sajao_dataset find                 # all pinned queries, no key needed
uv run python -m sajao_dataset find --query "2bhk flat tour pune" --per-query 5
YOUTUBE_API_KEY=... uv run python -m sajao_dataset find --backend data-api
```

Each pinned query (`src/sajao_dataset/queries.py`, English and Hindi) runs twice: once restricted to Creative Commons and once unrestricted. Empty-flat and new-build home tours are the priority category: their queries run first and their videos rank first everywhere, then Creative Commons first within each category. New videos are appended to `data/sources.jsonl`; videos already in the manifest are skipped. Videos shorter than 1 minute or longer than 1 hour are dropped.

| Backend | Needs | License field |
| --- | --- | --- |
| `yt-dlp` (default without a key) | Nothing | `creative_commons` from YouTube's own filter, otherwise `unknown` |
| `data-api` | `YOUTUBE_API_KEY` | Read from each video's status: `creative_commons` or `standard` |

Searching through the Data API costs 100 quota units per query and pass (about 9,800 units for the full set, most of the default 10,000 a day), so search stays on yt-dlp by default and only licenses come from the API.

## 1a. Record each video's license

```sh
uv run python -m sajao_dataset licenses            # runs automatically after find when YOUTUBE_API_KEY is set
uv run python -m sajao_dataset licenses --refresh  # recheck every video
```

Reads each video's `status` from the YouTube Data API, 50 videos per call at 1 quota unit (500 videos cost 10 units), and appends one line per video to `data/licenses.jsonl`: `creative_commons` or `standard`, and whether the video is still public. The ledger overrides what search inferred; private or deleted videos are never downloaded. The key is read from the environment and never printed or logged.

## 1b. Drop builder and designer promos

```sh
uv run python -m sajao_dataset prefilter
```

A free keyword pass before Gemini screening. It drops videos under 1 minute and videos whose title, channel or description match pinned promo terms (`src/sajao_dataset/prefilter.py`): sample and show flats, builder walkthroughs and project launches, sale and rent listings, designer reels and studio channels, 3D renders and Shorts. Channel-only terms (realty, developers, interiors and similar) apply to the channel name, not the title. It writes one decision per video, with the reason and the matched text, to `data/prefilter.jsonl`. Changing a term means a new `PREFILTER_VERSION`.

## 2. Screen with Gemini

```sh
export GCP_PROJECT_ID=...   # and GCP_SA_KEY (service account JSON, raw or base64), or gcloud ADC
uv run python -m sajao_dataset screen --limit 50 --cap-inr 500
```

Gemini on Vertex AI reads each public YouTube URL directly, so screening runs anywhere, including the cloud, and downloads nothing. It screens the videos the pre-filter kept, empty-flat and new-build tours first, then Creative Commons first, and answers keep or skip with a reason and room segments (`living_room`, `bedroom`, `kitchen`, `puja_room` and the other pinned room types in `src/sajao_dataset/screen.py`, with start, end and whether the room is furnished).

- **Models.** Through the model gateway: `gemini-3-flash-preview` first, `gemini-3.5-flash-lite` as the cheaper fallback, both at location `global`. `gemini-3.5-flash` is not used: Vertex AI refuses YouTube URLs for it.
- **Validation.** Room types must be in the pinned list, timestamps must be MM:SS and inside the screened window, a keep needs segments and a skip has none. An invalid answer is retried once, then the fallback is tried; if both fail the video is logged as failed and retried on the next run. Same-room segments that touch are merged; segments under 5 seconds are dropped.
- **Window.** Only the first 20 minutes of a video are screened, at 1 frame per second and low media resolution.
- **Cost.** About Rs 2 to 5 per video (Rs 24 for the 9 pilot videos, about 92 tokens per second of video). `--cap-inr` stops the run before the billed spend plus one worst-case video would pass it; calls whose answers were rejected count too.
- **Outputs.** `data/screening.jsonl` (one line per video, latest wins; reruns skip videos already answered by this `SCREEN_VERSION`), `data/segments.jsonl` (the kept room segments for `download --segments`, rewritten every run) and `data/screen_calls.jsonl` (the gateway's call log: outcomes, cost and latency, never prompts, URLs or keys).
- Credentials are read from the environment and never printed or logged.

## 3 and 4 in the cloud: download and frames on Modal

YouTube blocks downloads from cloud addresses (a plain Modal test failed on 5 of 5 videos with "Sign in to confirm you're not a bot"), so the cloud job sends yt-dlp, and the ffmpeg it drives, through a residential proxy. Find, licenses, prefilter and screen run first, anywhere, and leave `data/sources.jsonl`, `data/licenses.jsonl` and `data/segments.jsonl`.

```sh
uv run --with 'modal[api-proxy-support]==1.6.4' modal run services/dataset/cloud/app.py --limit-videos 5 --max-gb 0.5
```

- **Room segments only**, from screening: Creative Commons videos first, then the priority category. Unavailable videos are skipped.
- **720p, video only.**
- **GB cap per run** (`--max-gb`). The job counts the bytes the container receives while downloading (all of it through the proxy) and starts no segment whose estimate (2.5 Mbps plus 20 percent) would pass the cap.
- **Proxy.** The Modal secret `dataset-proxy` holds `YTDLP_PROXY_URL` (Decodo, India, sticky session). The URL is never printed or logged, and is redacted from error text before it reaches the ledger. The job checks the exit country first and downloads nothing unless it is India (`--require-country`). ffmpeg cannot open HTTPS through an authenticated proxy, so it goes through a local forwarder (pproxy) inside the container that holds the credentials.
- **Outputs** on the Modal volume `sajao-dataset`: `clips/`, `frames/`, `downloads.jsonl`, `frames.jsonl`, `frames_done.jsonl`. Reruns skip finished clips and frames. Each run's report is appended to `data/cloud_runs.jsonl` locally; log its proxy GB and spend in Notion Spends.

## 3. Download kept segments (home PC)

A personal PC on a home connection needs no proxy. Company-managed machines are not used.

### One-time setup (PowerShell)

```powershell
winget install --id Git.Git
winget install --id astral-sh.uv
winget install --id Gyan.FFmpeg        # ffmpeg and ffprobe; reopen PowerShell after
git clone https://github.com/Sahnijatin/sajao.git
cd sajao
uv sync --package sajao-dataset        # installs Python 3.13, yt-dlp and its JavaScript runtime
cd services\dataset
ffmpeg -version                        # must print a version
```

### Run

```powershell
$env:YOUTUBE_API_KEY = "<your key>"      # PowerShell; keeps the key out of files
uv run python -m sajao_dataset find      # also records licenses
uv run python -m sajao_dataset prefilter
uv run python -m sajao_dataset download --limit 50
```

With screening (run `screen` anywhere first and copy `data\segments.jsonl` to the PC), pass `--segments data\segments.jsonl` and only the kept room segments are fetched:

```powershell
uv run python -m sajao_dataset download --segments data\segments.jsonl
```

Without screening, each kept video contributes its first 10 minutes (`--head-s 600`): empty-flat and new-build tours first, then Creative Commons first.

- **Video only**, up to 1080p (`--max-height`). About 150 to 300 MB per 10 minutes at 1080p; the 50-video pilot needs roughly 10 GB free.
- **Resumable.** Each clip is checked with ffprobe (it must cover at least 80 percent of the requested range), checksummed and logged to `data\downloads.jsonl`. Rerunning skips finished clips and retries failed ones. A clip deleted from disk is fetched again.
- **Rate limited.** `--pause-s 5` between clips by default.
- **"Sign in to confirm you're not a bot"**: add `--cookies-from-browser edge` (or `chrome`, `firefox`) while signed in to YouTube in that browser. Close the browser first if Chrome reports a locked cookie database.
- **ffmpeg not on PATH**: pass `--ffmpeg "C:\path\to\ffmpeg\bin"`.
- The command exits with code 1 if any clip failed; the ledger has the error for each.

## 4. Sample frames

```powershell
uv run python -m sajao_dataset frames
```

Reads every finished clip in `data\downloads.jsonl` and writes JPEG frames to `data\frames\<video id>\<time in ms>.jpg`, with one line per frame in `data\frames.jsonl` (source time, room type, size, sharpness, faces blurred, checksum, hash).

1. One ffmpeg pass selects the first frame, every scene change (score above 0.20) and one frame every 2 s, scaled to at most 1280 px wide.
2. In time order, a frame is dropped if it is blurred (variance of the Laplacian below 60 on a 640 px grey copy), nearly identical to the last kept frame (16x16 thumbnails differ by 3 or less on average), or a repeat of any frame kept from the same video (256-bit difference hashes within 12 bits).
3. Faces are found with YuNet (downloaded once to `data\models`, checksum pinned) and blurred before the frame is written. Unblurred candidates exist only in a temporary folder that is always deleted.

Each finished clip is logged in `data\frames_done.jsonl`, so reruns skip it. Thresholds are pinned in `src/sajao_dataset/frames.py` under `SAMPLER_VERSION`. The selection pass and thumbnail dedup reuse ideas from bradautomates/claude-video (MIT).
