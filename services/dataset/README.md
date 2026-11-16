# Detector dataset pipeline

Builds a labelled set of real Indian rooms for the on-device detector. Every stage reads and writes a validated JSONL manifest under `data/` (never committed), so each stage is idempotent and resumes where it stopped.

| Stage | Command | Status |
| --- | --- | --- |
| 1. Find candidate videos | `find` | Ready |
| 1a. Record each video's license (YouTube Data API) | `licenses` | Ready |
| 1b. Drop builder and designer promos | `prefilter` | Ready |
| 2. Screen with Gemini (keep or skip, room timestamps) | | Next |
| 3. Download kept segments (Windows) | `download` | Ready |
| 4. Sample frames, drop near-duplicates and blur | | Next |
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
$env:YOUTUBE_API_KEY = "<your key>"      # PowerShell; keeps the key out of files
uv run python -m sajao_dataset find      # also records licenses
uv run python -m sajao_dataset prefilter
uv run python -m sajao_dataset download --limit 50
```

Without screening, each kept video contributes its first 10 minutes (`--head-s 600`): empty-flat and new-build tours first, then Creative Commons first. With screening, pass `--segments data\segments.jsonl` and only the kept room segments are fetched.

- **Video only**, up to 1080p (`--max-height`). About 150 to 300 MB per 10 minutes at 1080p; the 50-video pilot needs roughly 10 GB free.
- **Resumable.** Each clip is checked with ffprobe (it must cover at least 80 percent of the requested range), checksummed and logged to `data\downloads.jsonl`. Rerunning skips finished clips and retries failed ones. A clip deleted from disk is fetched again.
- **Rate limited.** `--pause-s 5` between clips by default.
- **"Sign in to confirm you're not a bot"**: add `--cookies-from-browser edge` (or `chrome`, `firefox`) while signed in to YouTube in that browser. Close the browser first if Chrome reports a locked cookie database.
- **ffmpeg not on PATH**: pass `--ffmpeg "C:\path\to\ffmpeg\bin"`.
- The command exits with code 1 if any clip failed; the ledger has the error for each.
