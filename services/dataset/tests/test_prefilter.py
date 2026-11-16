from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import HttpUrl

from sajao_dataset.cli import main
from sajao_dataset.manifest import SourceRecord, append_records
from sajao_dataset.prefilter import decide


def record(
    title: str = "My 2BHK home tour",
    *,
    channel: str | None = "Priya at home",
    description: str | None = "Welcome to our rented flat",
    duration_s: int | None = 600,
    video_id: str = "aaaaaaaaaaa",
) -> SourceRecord:
    return SourceRecord(
        video_id=video_id,
        url=HttpUrl(f"https://www.youtube.com/watch?v={video_id}"),
        title=title,
        channel=channel,
        channel_id=None,
        description=description,
        duration_s=duration_s,
        license="unknown",
        license_evidence="none",
        query="q",
        query_set="t",
        found_by="yt-dlp",
        found_at=datetime(2000, 1, 1, tzinfo=UTC),
    )


def test_real_home_tours_are_kept() -> None:
    assert decide(record()).keep
    assert decide(record("Builder floor home tour in Delhi | 3BHK", description=None)).keep
    assert decide(record(duration_s=None)).keep


@pytest.mark.parametrize(
    ("kwargs", "reason", "field"),
    [
        ({"title": "2BHK Sample Flat at Rohan Anand"}, "sample_flat", "title"),
        ({"title": "Show flat tour"}, "show_flat", "title"),
        ({"title": "Showhome visit Thane"}, "show_flat", "title"),
        (
            {"description": "Complete 3D walkthrough of the project"},
            "builder_walkthrough",
            "description",
        ),
        (
            {"description": "New launch in Wakad, RERA approved"},
            "builder_walkthrough",
            "description",
        ),
        ({"channel": "Skyline Realty"}, "builder_walkthrough", "channel"),
        ({"channel": "Dizzartzz Interiors"}, "designer_reel", "channel"),
        ({"title": "Best interior designer in Pune"}, "designer_reel", "title"),
        ({"description": "#interiordesign #homedecor"}, "designer_reel", "description"),
        ({"title": "Living room 3D rendering"}, "render_3d", "title"),
        ({"title": "Bedroom renders by our studio"}, "render_3d", "title"),
        ({"title": "Tiny kitchen #shorts"}, "shorts", "title"),
        ({"title": "Individual house for sale in Jaipur"}, "sale_listing", "title"),
        ({"title": "1BHK flat, LOAN UPTO 90%"}, "sale_listing", "title"),
        ({"channel": "BricksandRoof Realestate"}, "builder_walkthrough", "channel"),
        ({"channel": "Be Link Homes Pvt. Ltd"}, "builder_walkthrough", "channel"),
        ({"channel": "#interiorwork_studio"}, "designer_reel", "channel"),
        ({"title": "2 & 3 BHK flats for rent, Panjagutta"}, "sale_listing", "title"),
        ({"channel": "Prop Vestors"}, "builder_walkthrough", "channel"),
        ({"duration_s": 45}, "too_short", "duration"),
    ],
)
def test_promos_are_dropped_with_a_reason(
    kwargs: dict[str, object], reason: str, field: str
) -> None:
    decision = decide(record(**kwargs))  # type: ignore[arg-type]
    assert not decision.keep
    assert (decision.reason, decision.field) == (reason, field)
    assert decision.matched


def test_channel_terms_do_not_apply_to_titles() -> None:
    # "properties" in a title is ordinary language, not a business name.
    assert decide(record("Rental flat properties we looked at, final home tour")).keep


def test_cli_prefilter_writes_one_decision_per_video(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = tmp_path / "sources.jsonl"
    out = tmp_path / "prefilter.jsonl"
    append_records(manifest, [record(), record("Sample flat", video_id="bbbbbbbbbbb")])

    assert main(["prefilter", "--manifest", str(manifest), "--out", str(out)]) == 0
    assert main(["prefilter", "--manifest", str(manifest), "--out", str(out)]) == 0

    assert len(out.read_text().splitlines()) == 2
    assert "1 of 2 kept" in capsys.readouterr().out
