# Detector dataset pipeline

Builds a labelled set of real Indian rooms for the on-device detector. Every stage reads and writes a validated JSONL manifest under `data/` (never committed), so each stage is idempotent and resumes where it stopped.

| Stage | Command | Status |
| --- | --- | --- |
| 1. Find candidate videos | `find` | Ready |
| 1b. Drop builder and designer promos | `prefilter` | Ready |
| 2. Screen with Gemini (keep or skip, room timestamps) | | Next |
| 3. Download kept segments (Windows) | | Next |
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
