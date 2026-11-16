from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import HttpUrl

from sajao_dataset.cli import main
from sajao_dataset.download import plan_head_segments
from sajao_dataset.licenses import (
    DataApiVideos,
    append_licenses,
    apply_licenses,
    check_licenses,
    read_licenses,
)
from sajao_dataset.manifest import SourceRecord, append_records
from sajao_dataset.prefilter import Decision
from sajao_dataset.queries import ALL_QUERIES, PRIORITY_QUERIES, category_of

NOW = datetime(2000, 1, 1, tzinfo=UTC)


def source(video_id: str, license: str = "unknown", category: str = "general") -> SourceRecord:
    return SourceRecord.model_validate(
        {
            "video_id": video_id,
            "url": HttpUrl(f"https://www.youtube.com/watch?v={video_id}"),
            "title": "t",
            "channel": None,
            "channel_id": None,
            "duration_s": 600,
            "license": license,
            "license_evidence": "none",
            "query": "q",
            "query_set": "s",
            "category": category,
            "found_by": "yt-dlp",
            "found_at": NOW,
        }
    )


class FakeVideos:
    def __init__(self, statuses: dict[str, dict[str, Any]]) -> None:
        self.statuses_by_id = statuses
        self.calls: list[int] = []

    def statuses(self, ids: Sequence[str]) -> dict[str, dict[str, Any]]:
        self.calls.append(len(ids))
        return {i: self.statuses_by_id[i] for i in ids if i in self.statuses_by_id}


def test_check_licenses_batches_by_50_and_marks_unavailable_videos() -> None:
    ids = [f"v{i:010d}" for i in range(120)]
    statuses = {i: {"license": "youtube", "privacyStatus": "public"} for i in ids}
    statuses[ids[0]] = {"license": "creativeCommon", "privacyStatus": "public"}
    statuses[ids[1]] = {"license": "youtube", "privacyStatus": "private"}
    del statuses[ids[2]]  # deleted from YouTube
    api = FakeVideos(statuses)

    records = {r.video_id: r for r in check_licenses(api, ids + ids[:5], now=NOW)}

    assert api.calls == [50, 50, 20]  # duplicates are checked once
    assert (records[ids[0]].license, records[ids[0]].availability) == (
        "creative_commons",
        "available",
    )
    assert records[ids[1]].availability == "unavailable"
    assert (records[ids[2]].license, records[ids[2]].availability) == ("unknown", "unavailable")
    assert records[ids[3]].license == "standard"


def test_ledger_latest_wins_and_apply_overrides_search_and_drops_unavailable(
    tmp_path: Path,
) -> None:
    path = tmp_path / "licenses.jsonl"
    first = check_licenses(
        FakeVideos({"aaaaaaaaaaa": {"license": "youtube", "privacyStatus": "public"}}),
        ["aaaaaaaaaaa"],
        now=NOW,
    )
    later = check_licenses(
        FakeVideos({"aaaaaaaaaaa": {"license": "creativeCommon", "privacyStatus": "public"}}),
        ["aaaaaaaaaaa"],
        now=NOW,
    )
    gone = check_licenses(FakeVideos({}), ["bbbbbbbbbbb"], now=NOW)
    append_licenses(path, first + later + gone)

    ledger = read_licenses(path)
    applied = apply_licenses(
        [source("aaaaaaaaaaa"), source("bbbbbbbbbbb"), source("ccccccccccc")], ledger
    )

    assert [(s.video_id, s.license, s.license_evidence) for s in applied] == [
        ("aaaaaaaaaaa", "creative_commons", "data_api"),
        ("ccccccccccc", "unknown", "none"),  # not checked yet: kept as found
    ]


def test_data_api_videos_never_puts_the_key_in_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["part"] == "status"
        return httpx.Response(403, json={"error": "quota"})

    api = DataApiVideos("secret-key-value", httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(RuntimeError) as error:
        api.statuses(["aaaaaaaaaaa"])
    assert "secret-key-value" not in str(error.value)
    assert "403" in str(error.value)


def test_priority_queries_come_first_and_map_to_their_category() -> None:
    assert ALL_QUERIES[: len(PRIORITY_QUERIES)] == PRIORITY_QUERIES
    assert len(set(ALL_QUERIES)) == len(ALL_QUERIES)
    assert category_of("empty flat tour") == "empty_new_build"
    assert category_of("indian home tour") == "general"


def test_plan_puts_priority_category_first_then_creative_commons() -> None:
    sources = [
        source("generalcc00", "creative_commons"),
        source("emptystd000", "standard", "empty_new_build"),
        source("emptycc0000", "creative_commons", "empty_new_build"),
        source("generalstd0", "standard"),
    ]
    decisions = [
        Decision(video_id=s.video_id, keep=True, reason=None, field=None, matched=None)
        for s in sources
    ]
    plan = plan_head_segments(sources, decisions, head_s=600, limit=10)
    assert [s.video_id for s in plan] == [
        "emptycc0000",
        "emptystd000",
        "generalcc00",
        "generalstd0",
    ]


def test_cli_licenses_skips_recorded_videos_unless_refresh(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest, ledger = tmp_path / "sources.jsonl", tmp_path / "licenses.jsonl"
    append_records(manifest, [source("aaaaaaaaaaa"), source("bbbbbbbbbbb")])
    api = FakeVideos({"aaaaaaaaaaa": {"license": "creativeCommon", "privacyStatus": "public"}})
    monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")
    monkeypatch.setattr("sajao_dataset.cli.DataApiVideos", lambda key: api)

    args = ["licenses", "--manifest", str(manifest), "--licenses", str(ledger)]
    assert main(args) == 0
    assert main(args) == 0
    assert main([*args, "--refresh"]) == 0

    assert api.calls == [2, 2]  # second run had nothing to check
    assert len(ledger.read_text().splitlines()) == 4
