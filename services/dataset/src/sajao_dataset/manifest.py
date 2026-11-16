"""The source manifest: one JSON line per candidate video.

The manifest is append only. Every line is validated on write and on read, so
later stages can trust it. A rerun of the finder adds only videos it has not
seen before.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

License = Literal["creative_commons", "standard", "unknown"]
"""creative_commons: CC BY reuse allowed. standard: YouTube's standard license.
unknown: not checked yet (a yt-dlp search without the Creative Commons filter)."""

LicenseEvidence = Literal["data_api", "cc_search_filter", "none"]
"""How the license was established: the Data API status field, YouTube's own
Creative Commons search filter, or nothing yet."""


FoundBy = Literal["yt-dlp", "youtube-data-api"]


class SourceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source: Literal["youtube"] = "youtube"
    video_id: str = Field(pattern=r"^[A-Za-z0-9_-]{11}$")
    url: HttpUrl
    title: str
    channel: str | None
    channel_id: str | None
    description: str | None = None
    """The description, or the snippet of it that search returns."""
    duration_s: int | None = Field(ge=0)
    license: License
    license_evidence: LicenseEvidence
    query: str
    query_set: str
    found_by: FoundBy
    found_at: datetime
    use: Literal["internal_training_only"] = "internal_training_only"


def read_manifest(path: Path) -> list[SourceRecord]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [SourceRecord.model_validate_json(line) for line in f if line.strip()]


def append_records(path: Path, records: Iterable[SourceRecord]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("a", encoding="utf-8", newline="\n") as f:
        for record in records:
            f.write(record.model_dump_json() + "\n")
            count += 1
    return count
