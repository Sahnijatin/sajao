from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import httpx
import pytest
from pydantic import ValidationError

from sajao_dataset.cli import main
from sajao_dataset.manifest import SourceRecord, append_records, read_manifest
from sajao_dataset.youtube import DataApiSearch, Hit, YtDlpSearch, find, parse_iso_duration

NOW = datetime(2000, 1, 1, tzinfo=UTC)


def hit(video_id: str, *, cc: bool, duration: int | None = 600) -> Hit:
    return Hit(
        video_id=video_id,
        title=f"tour {video_id}",
        channel="A channel",
        channel_id="UC123",
        duration_s=duration,
        license="creative_commons" if cc else "unknown",
        license_evidence="cc_search_filter" if cc else "none",
    )


class FakeSearch:
    name: Literal["yt-dlp"] = "yt-dlp"

    def __init__(self, cc: list[Hit], any_: list[Hit]) -> None:
        self.cc, self.any = cc, any_
        self.calls: list[tuple[str, bool]] = []

    def search(self, query: str, *, creative_commons_only: bool, limit: int) -> list[Hit]:
        self.calls.append((query, creative_commons_only))
        return (self.cc if creative_commons_only else self.any)[:limit]


def test_find_runs_both_passes_dedups_and_puts_creative_commons_first() -> None:
    search = FakeSearch(
        cc=[hit("ccccccccccc", cc=True)],
        any_=[
            hit("aaaaaaaaaaa", cc=False),
            hit("ccccccccccc", cc=False),
        ],
    )
    records = find(
        search, ["q1"], query_set="t", seen=set(), per_query=10, max_new=10, now=lambda: NOW
    )

    assert search.calls == [("q1", True), ("q1", False)]
    assert [r.video_id for r in records] == ["ccccccccccc", "aaaaaaaaaaa"]
    assert records[0].license == "creative_commons"
    assert records[0].license_evidence == "cc_search_filter"
    assert all(r.use == "internal_training_only" for r in records)


def test_find_skips_seen_and_out_of_range_durations_and_caps_new() -> None:
    search = FakeSearch(
        cc=[],
        any_=[
            hit("seen0000000", cc=False),
            hit("short000000", cc=False, duration=30),
            hit("long0000000", cc=False, duration=5 * 3600),
            hit("nodur000000", cc=False, duration=None),
            hit("ok000000000", cc=False),
        ],
    )
    records = find(search, ["q"], query_set="t", seen={"seen0000000"}, per_query=10, max_new=1)
    assert [r.video_id for r in records] == ["nodur000000"]


def test_manifest_round_trip_and_validation(tmp_path: Path) -> None:
    path = tmp_path / "m.jsonl"
    records = find(
        FakeSearch([hit("ccccccccccc", cc=True)], []),
        ["q"],
        query_set="t",
        seen=set(),
        per_query=5,
        max_new=5,
        now=lambda: NOW,
    )
    append_records(path, records)
    append_records(path, [])
    assert read_manifest(path) == records

    with pytest.raises(ValidationError):
        SourceRecord.model_validate({**records[0].model_dump(), "video_id": "bad"})
    with pytest.raises(ValidationError):
        SourceRecord.model_validate({**records[0].model_dump(), "use": "redistribute"})


def test_yt_dlp_search_builds_cc_url_and_drops_shorts() -> None:
    urls: list[str] = []

    def extract(url: str, limit: int) -> dict[str, Any]:
        urls.append(url)
        return {
            "entries": [
                {
                    "id": "aaaaaaaaaaa",
                    "title": "Home tour",
                    "channel": "C",
                    "channel_id": "UC1",
                    "duration": 512.0,
                    "url": "https://www.youtube.com/watch?v=aaaaaaaaaaa",
                },
                {"id": "UCJ_ULnl7vBDUhpKWkt6Eyfg", "ie_key": "YoutubeTab", "title": "A channel"},
                {"id": "PLxxxxxxxxxxxxxxxx", "ie_key": "YoutubeTab", "title": "A playlist"},
                {
                    "id": "bbbbbbbbbbb",
                    "title": "Short",
                    "url": "https://www.youtube.com/shorts/bbbbbbbbbbb",
                },
            ]
        }

    hits = YtDlpSearch(extract).search("2bhk tour", creative_commons_only=True, limit=5)
    assert urls == ["https://www.youtube.com/results?search_query=2bhk+tour&sp=EgIwAQ%3D%3D"]
    assert [h.video_id for h in hits] == ["aaaaaaaaaaa"]
    assert hits[0].duration_s == 512
    assert hits[0].license == "creative_commons"

    YtDlpSearch(extract).search("x", creative_commons_only=False, limit=5)
    assert urls[-1] == "https://www.youtube.com/results?search_query=x"


def test_data_api_search_reads_license_and_duration() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("/search"):
            return httpx.Response(
                200,
                json={
                    "items": [
                        {"id": {"videoId": "aaaaaaaaaaa"}},
                        {"id": {"videoId": "bbbbbbbbbbb"}},
                    ]
                },
            )
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": "aaaaaaaaaaa",
                        "snippet": {"title": "T", "channelTitle": "C", "channelId": "U"},
                        "contentDetails": {"duration": "PT12M5S"},
                        "status": {"license": "creativeCommon"},
                    },
                    {
                        "id": "bbbbbbbbbbb",
                        "snippet": {"title": "T2"},
                        "contentDetails": {"duration": "PT1H"},
                        "status": {"license": "youtube"},
                    },
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    hits = DataApiSearch("test-key", client).search("q", creative_commons_only=False, limit=80)

    assert seen[0].url.params["maxResults"] == "50"
    assert seen[0].url.params["videoLicense"] == "any"
    assert seen[0].url.params["regionCode"] == "IN"
    assert [(h.license, h.duration_s) for h in hits] == [
        ("creative_commons", 725),
        ("standard", 3600),
    ]
    assert all(h.license_evidence == "data_api" for h in hits)


@pytest.mark.parametrize(
    ("value", "seconds"),
    [
        ("PT45S", 45),
        ("PT3M", 180),
        ("PT1H2M3S", 3723),
        ("P1DT1S", 86401),
        ("", None),
        ("bad", None),
    ],
)
def test_parse_iso_duration(value: str, seconds: int | None) -> None:
    assert parse_iso_duration(value) == seconds


def test_cli_find_appends_only_new(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = FakeSearch(cc=[hit("ccccccccccc", cc=True)], any_=[hit("aaaaaaaaaaa", cc=False)])
    monkeypatch.setattr("sajao_dataset.cli._backend", lambda choice: fake)
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    manifest = tmp_path / "sources.jsonl"

    assert main(["find", "--manifest", str(manifest), "--query", "q"]) == 0
    assert main(["find", "--manifest", str(manifest), "--query", "q"]) == 0

    assert [r.video_id for r in read_manifest(manifest)] == ["ccccccccccc", "aaaaaaaaaaa"]
    assert "0 new videos" in capsys.readouterr().out
