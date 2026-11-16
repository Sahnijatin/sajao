"""Find candidate YouTube home tour videos.

Two search backends return the same `Hit`:

- `YtDlpSearch` needs no key. It reads YouTube's search results page. The
  Creative Commons pass uses YouTube's own license filter, so those hits carry
  a known license; hits from the unfiltered pass are "unknown".
- `DataApiSearch` uses the YouTube Data API v3 and reads each video's license
  from its status. Each search costs 100 quota units (10,000 a day by default).

Each query runs twice: once restricted to Creative Commons, once unrestricted,
so Creative Commons videos surface even when they rank low.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, Protocol
from urllib.parse import quote_plus

import httpx
from pydantic import HttpUrl

from sajao_dataset.manifest import FoundBy, License, LicenseEvidence, SourceRecord

MIN_DURATION_S = 60
MAX_DURATION_S = 60 * 60

_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")

# YouTube's search filter for "Creative Commons" (the `sp` URL parameter).
CC_FILTER = "EgIwAQ%3D%3D"


@dataclass(frozen=True)
class Hit:
    video_id: str
    title: str
    channel: str | None
    channel_id: str | None
    duration_s: int | None
    license: License
    license_evidence: LicenseEvidence
    description: str | None = None


class Search(Protocol):
    @property
    def name(self) -> FoundBy: ...

    def search(self, query: str, *, creative_commons_only: bool, limit: int) -> list[Hit]: ...


class YtDlpSearch:
    name: Literal["yt-dlp"] = "yt-dlp"

    def __init__(self, extract: Callable[[str, int], dict[str, Any]] | None = None) -> None:
        self._extract = extract or _yt_dlp_extract

    def search(self, query: str, *, creative_commons_only: bool, limit: int) -> list[Hit]:
        url = f"https://www.youtube.com/results?search_query={quote_plus(query)}"
        if creative_commons_only:
            url += f"&sp={CC_FILTER}"
        info = self._extract(url, limit)
        hits = []
        for entry in info.get("entries") or []:
            video_id = entry.get("id")
            # Search pages also list channels, playlists and Shorts; keep only videos.
            if (
                entry.get("ie_key", "Youtube") != "Youtube"
                or not isinstance(video_id, str)
                or not _VIDEO_ID.match(video_id)
                or "/shorts/" in str(entry.get("url", ""))
            ):
                continue
            duration = entry.get("duration")
            hits.append(
                Hit(
                    video_id=video_id,
                    title=str(entry.get("title") or ""),
                    channel=entry.get("channel") or entry.get("uploader"),
                    channel_id=entry.get("channel_id"),
                    duration_s=int(duration) if duration is not None else None,
                    license="creative_commons" if creative_commons_only else "unknown",
                    license_evidence="cc_search_filter" if creative_commons_only else "none",
                    description=entry.get("description"),
                )
            )
        return hits[:limit]


def _yt_dlp_extract(url: str, limit: int) -> dict[str, Any]:
    import yt_dlp

    options = {
        "extract_flat": "in_playlist",
        "playlistend": limit,
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
    }
    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=False)
    return dict(info or {})


class DataApiSearch:
    name: Literal["youtube-data-api"] = "youtube-data-api"
    BASE = "https://www.googleapis.com/youtube/v3"

    def __init__(self, api_key: str, client: httpx.Client | None = None) -> None:
        self._key = api_key
        self._client = client or httpx.Client(timeout=30)

    def search(self, query: str, *, creative_commons_only: bool, limit: int) -> list[Hit]:
        found = self._get(
            "search",
            part="snippet",
            q=query,
            type="video",
            regionCode="IN",
            maxResults=min(limit, 50),
            videoLicense="creativeCommon" if creative_commons_only else "any",
        )
        ids = [item["id"]["videoId"] for item in found.get("items", [])]
        if not ids:
            return []
        details = self._get("videos", part="snippet,contentDetails,status", id=",".join(ids))
        hits = []
        for item in details.get("items", []):
            status = item.get("status", {}).get("license")
            snippet = item.get("snippet", {})
            hits.append(
                Hit(
                    video_id=item["id"],
                    title=snippet.get("title", ""),
                    channel=snippet.get("channelTitle"),
                    channel_id=snippet.get("channelId"),
                    duration_s=parse_iso_duration(item.get("contentDetails", {}).get("duration")),
                    license=_DATA_API_LICENSE.get(status or "", "unknown"),
                    license_evidence="data_api" if status else "none",
                    description=snippet.get("description"),
                )
            )
        return hits

    def _get(self, path: str, **params: str | int) -> dict[str, Any]:
        # The key is passed as a parameter and never logged.
        response = self._client.get(f"{self.BASE}/{path}", params={**params, "key": self._key})
        response.raise_for_status()
        body: dict[str, Any] = response.json()
        return body


_DATA_API_LICENSE: dict[str, License] = {
    "creativeCommon": "creative_commons",
    "youtube": "standard",
}

_ISO = re.compile(r"^P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$")


def parse_iso_duration(value: str | None) -> int | None:
    if not value:
        return None
    match = _ISO.match(value)
    if not match:
        return None
    days, hours, minutes, seconds = (int(g) if g else 0 for g in match.groups())
    return ((days * 24 + hours) * 60 + minutes) * 60 + seconds


_LICENSE_RANK = {"creative_commons": 0, "standard": 1, "unknown": 2}


def find(
    search: Search,
    queries: Iterable[str],
    *,
    query_set: str,
    seen: set[str],
    per_query: int,
    max_new: int,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> list[SourceRecord]:
    """Run every query in both license passes and return new records, Creative Commons first.

    Videos in `seen` are skipped. When a video turns up in several passes, the
    record with the strongest license evidence wins.
    """
    best: dict[str, SourceRecord] = {}
    for query in queries:
        for cc_only in (True, False):
            for hit in search.search(query, creative_commons_only=cc_only, limit=per_query):
                if hit.video_id in seen or not _duration_ok(hit.duration_s):
                    continue
                record = SourceRecord(
                    video_id=hit.video_id,
                    url=HttpUrl(f"https://www.youtube.com/watch?v={hit.video_id}"),
                    title=hit.title,
                    channel=hit.channel,
                    channel_id=hit.channel_id,
                    description=hit.description,
                    duration_s=hit.duration_s,
                    license=hit.license,
                    license_evidence=hit.license_evidence,
                    query=query,
                    query_set=query_set,
                    found_by=search.name,
                    found_at=now(),
                )
                current = best.get(hit.video_id)
                if (
                    current is None
                    or _LICENSE_RANK[record.license] < _LICENSE_RANK[current.license]
                ):
                    best[hit.video_id] = record
    ordered = sorted(best.values(), key=lambda r: _LICENSE_RANK[r.license])
    return ordered[:max_new]


def _duration_ok(duration_s: int | None) -> bool:
    return duration_s is None or MIN_DURATION_S <= duration_s <= MAX_DURATION_S
