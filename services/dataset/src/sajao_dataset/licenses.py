"""Record each video's license from the YouTube Data API.

Search stays free (yt-dlp). This pass looks up every video in the manifest
with `videos.list`, 50 ids per call at 1 quota unit each, and writes one line
per video to an append-only ledger. The ledger is the source of truth for
licenses: it overrides what search inferred, and videos that are private,
deleted or not embeddable are marked unavailable and never downloaded.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Protocol

import httpx
from pydantic import BaseModel, ConfigDict

from sajao_dataset.manifest import License, SourceRecord

BATCH = 50

_API_LICENSE: dict[str, License] = {"creativeCommon": "creative_commons", "youtube": "standard"}

Availability = Literal["available", "unavailable"]


class LicenseRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    video_id: str
    license: License
    availability: Availability
    privacy_status: str | None
    """public, unlisted or private; None when the video no longer exists."""
    checked_at: datetime
    evidence: Literal["data_api"] = "data_api"


class VideosApi(Protocol):
    def statuses(self, ids: Sequence[str]) -> dict[str, dict[str, Any]]:
        """Return the `status` object for each id the API still knows."""
        ...


class DataApiVideos:
    URL = "https://www.googleapis.com/youtube/v3/videos"

    def __init__(self, api_key: str, client: httpx.Client | None = None) -> None:
        self._key = api_key
        self._client = client or httpx.Client(timeout=30)

    def statuses(self, ids: Sequence[str]) -> dict[str, dict[str, Any]]:
        # The key travels as a parameter and is never logged or printed.
        response = self._client.get(
            self.URL, params={"part": "status", "id": ",".join(ids), "key": self._key}
        )
        if response.is_error:
            # Never include the request URL in errors: it carries the key.
            raise RuntimeError(f"YouTube Data API returned HTTP {response.status_code}")
        return {item["id"]: item.get("status", {}) for item in response.json().get("items", [])}


def check_licenses(
    api: VideosApi, video_ids: Iterable[str], *, now: datetime | None = None
) -> list[LicenseRecord]:
    ids = list(dict.fromkeys(video_ids))
    at = now or datetime.now(UTC)
    out: list[LicenseRecord] = []
    for start in range(0, len(ids), BATCH):
        batch = ids[start : start + BATCH]
        statuses = api.statuses(batch)
        for video_id in batch:
            status = statuses.get(video_id)
            if status is None:
                out.append(_record(video_id, "unknown", "unavailable", None, at))
                continue
            license_ = _API_LICENSE.get(status.get("license", ""), "unknown")
            usable = (
                status.get("privacyStatus") in ("public", "unlisted")
                and status.get("uploadStatus", "processed") == "processed"
            )
            out.append(
                _record(
                    video_id,
                    license_,
                    "available" if usable else "unavailable",
                    status.get("privacyStatus"),
                    at,
                )
            )
    return out


def _record(
    video_id: str,
    license_: License,
    availability: Availability,
    privacy: str | None,
    at: datetime,
) -> LicenseRecord:
    return LicenseRecord(
        video_id=video_id,
        license=license_,
        availability=availability,
        privacy_status=privacy,
        checked_at=at,
    )


def read_licenses(path: Path) -> dict[str, LicenseRecord]:
    """Latest record per video wins."""
    if not path.exists():
        return {}
    latest: dict[str, LicenseRecord] = {}
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                record = LicenseRecord.model_validate_json(line)
                latest[record.video_id] = record
    return latest


def append_licenses(path: Path, records: Iterable[LicenseRecord]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("a", encoding="utf-8", newline="\n") as f:
        for record in records:
            f.write(record.model_dump_json() + "\n")
            count += 1
    return count


def apply_licenses(
    sources: Iterable[SourceRecord], licenses: dict[str, LicenseRecord]
) -> list[SourceRecord]:
    """Sources with the API license applied; unavailable videos are dropped."""
    out = []
    for source in sources:
        checked = licenses.get(source.video_id)
        if checked is None:
            out.append(source)
        elif checked.availability == "available":
            out.append(
                source.model_copy(
                    update={"license": checked.license, "license_evidence": "data_api"}
                )
            )
    return out
