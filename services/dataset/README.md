# Detector dataset pipeline

Builds a labelled set of real Indian rooms for the on-device detector. Every stage reads and writes a validated JSONL manifest under `data/` (never committed), so each stage is idempotent and resumes where it stopped.

| Stage | Command | Status |
| --- | --- | --- |
| 1. Find candidate videos | `find` | Ready |
| 1b. Drop builder and designer promos | `prefilter` | Ready |
| 2. Screen with Gemini (keep or skip, room timestamps) | | Next |
| 3. Download kept segments (Windows) | `download` | Ready |
| 4. Sample frames, drop near-duplicates and blur, blur faces | `frames` | Ready |
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

Each pinned query (`src/sajao_dataset/queries.py`, English and Hindi) runs twice: once restricted to Creative Commons and once unrestricted. New videos are appended to `data/sources.jsonl`, Creative Commons first; videos already in the manifest are skipped. Videos shorter than 1 minute or longer than 1 hour are dropped.

| Backend | Needs | License field |
| --- | --- | --- |
| `yt-dlp` (default without a key) | Nothing | `creative_commons` from YouTube's own filter, otherwise `unknown` |
| `data-api` | `YOUTUBE_API_KEY` | Read from each video's status: `creative_commons` or `standard` |

The Data API costs 100 quota units per search; the full query set uses about 7,200 of the default 10,000 a day.

## 1b. Drop builder and designer promos

```sh
uv run python -m sajao_dataset prefilter
```

A free keyword pass before Gemini screening. It drops videos under 1 minute and videos whose title, channel or description match pinned promo terms (`src/sajao_dataset/prefilter.py`): sample and show flats, builder walkthroughs and project launches, sale and rent listings, designer reels and studio channels, 3D renders and Shorts. Channel-only terms (realty, developers, interiors and similar) apply to the channel name, not the title. It writes one decision per video, with the reason and the matched text, to `data/prefilter.jsonl`. Changing a term means a new `PREFILTER_VERSION`.

## 3. Download kept segments (Windows PC)

YouTube blocks downloads from cloud servers, so this stage runs on a home PC.

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
uv run python -m sajao_dataset find
uv run python -m sajao_dataset prefilter
uv run python -m sajao_dataset download --limit 50
```

Without screening, each kept video contributes its first 10 minutes (`--head-s 600`), Creative Commons first. With screening, pass `--segments data\segments.jsonl` and only the kept room segments are fetched.

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
