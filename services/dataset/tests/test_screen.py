import base64
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import HttpUrl

from sajao_dataset.cli import main
from sajao_dataset.gemini import (
    GEMINI_3_FLASH,
    GEMINI_35_FLASH_LITE,
    VertexGeminiProvider,
    parse_service_account,
)
from sajao_dataset.manifest import SourceRecord
from sajao_dataset.prefilter import Decision
from sajao_dataset.screen import (
    MAX_WINDOW_S,
    PROMPT_ID,
    SCREEN_VERSION,
    RoomSegment,
    ScreenRecord,
    build_request,
    kept_segments,
    mmss,
    parse_output,
    plan_screening,
    read_screening,
    screen_all,
    seconds,
    tidy_segments,
)
from sajao_gateway import (
    InMemoryCallLog,
    InMemorySpendLedger,
    InvalidOutputError,
    ModelGateway,
    ModelRequest,
    ProviderError,
    ProviderResult,
    RetryPolicy,
    SpendCaps,
)
from sajao_gateway.types import Modality

NOW = datetime(2000, 1, 1, tzinfo=UTC)
TOKEN = "test-token-not-real"  # noqa: S105


def source(
    video_id: str,
    *,
    license: str = "standard",
    category: str = "general",
    duration_s: int | None = 600,
) -> SourceRecord:
    return SourceRecord.model_validate(
        {
            "video_id": video_id,
            "url": HttpUrl(f"https://www.youtube.com/watch?v={video_id}"),
            "title": "t",
            "channel": None,
            "channel_id": None,
            "duration_s": duration_s,
            "license": license,
            "license_evidence": "data_api",
            "query": "q",
            "query_set": "s",
            "category": category,
            "found_by": "yt-dlp",
            "found_at": NOW,
        }
    )


def keep_decision(video_id: str, keep: bool = True) -> Decision:
    return Decision.model_validate(
        {
            "video_id": video_id,
            "keep": keep,
            "reason": None if keep else "builder_walkthrough",
            "field": None,
            "matched": None,
        }
    )


def answer(keep: bool = True, segments: list[tuple[str, str, str]] | None = None) -> dict[str, Any]:
    if segments is None:
        segments = [("kitchen", "00:10", "00:40")] if keep else []
    return {
        "keep": keep,
        "reason": "r",
        "segments": [
            {"room_type": room, "start": start, "end": end, "furnished": False}
            for room, start, end in segments
        ],
    }


# Timestamps


def test_seconds_parses_mm_ss_and_h_mm_ss() -> None:
    assert seconds("00:00") == 0
    assert seconds("07:05") == 425
    assert seconds("125:00") == 7500
    assert seconds("1:02:03") == 3723
    assert mmss(425.9) == "07:05"


@pytest.mark.parametrize("bad", ["", "7", "07:60", "07.05", "-1:00", "1:2:3", "abc"])
def test_seconds_rejects_anything_else(bad: str) -> None:
    with pytest.raises(ValueError):
        seconds(bad)


# Output validation


def test_parse_output_converts_timestamps() -> None:
    parsed = parse_output(answer(segments=[("bedroom", "01:00", "02:30")]), 600)
    assert parsed.keep
    assert parsed.segments[0].start_s == 60
    assert parsed.segments[0].end_s == 150


@pytest.mark.parametrize(
    ("output", "message"),
    [
        (answer(keep=True, segments=[]), "keep without segments"),
        (answer(keep=False, segments=[("kitchen", "00:10", "00:20")]), "skip with segments"),
        (answer(segments=[("kitchen", "00:20", "00:10")]), "ends before"),
        (answer(segments=[("kitchen", "09:00", "10:05")]), "past the end"),
        (answer(segments=[("kitchen", "10", "20")]), "MM:SS"),
        (answer(segments=[("garage", "00:10", "00:20")]), "schema"),
        ({"keep": True, "reason": "r"}, "schema"),
        ({**answer(), "extra": 1}, "schema"),
        ({**answer(), "reason": ""}, "schema"),
    ],
)
def test_parse_output_rejects_untrustworthy_answers(output: Any, message: str) -> None:
    with pytest.raises(InvalidOutputError, match=message):
        parse_output(output, 600)


def test_parse_output_clamps_ends_just_past_the_window() -> None:
    parsed = parse_output(answer(segments=[("kitchen", "09:50", "10:01")]), 600)
    assert parsed.segments[0].end_s == 600


def test_tidy_segments_merges_same_room_and_drops_short_ones() -> None:
    def seg(room: str, start: float, end: float, furnished: bool = False) -> RoomSegment:
        return RoomSegment(room_type=room, start_s=start, end_s=end, furnished=furnished)  # type: ignore[arg-type]

    tidy = tidy_segments(
        [
            seg("kitchen", 30, 40, furnished=True),
            seg("kitchen", 10, 29),
            seg("bedroom", 50, 53),  # too short
            seg("bedroom", 60, 80),
            seg("kitchen", 81, 90),  # a different room in between: not merged
        ]
    )
    assert [(s.room_type, s.start_s, s.end_s, s.furnished) for s in tidy] == [
        ("kitchen", 10, 40, True),
        ("bedroom", 60, 80, False),
        ("kitchen", 81, 90, False),
    ]


# Planning


def record(video_id: str, status: str, version: str = SCREEN_VERSION) -> ScreenRecord:
    return ScreenRecord(
        video_id=video_id,
        screen_version=version,
        prompt_id=PROMPT_ID,
        status=status,  # type: ignore[arg-type]
        reason="r",
        segments=[],
        window_s=600,
        provider=None,
        model=None,
        cost_micro_inr=0,
        screened_at=NOW,
    )


def test_plan_screening_orders_skips_done_and_retries_failed() -> None:
    sources = [
        source("aaaaaaaaaaa"),
        source("bbbbbbbbbbb", license="creative_commons"),
        source("ccccccccccc", category="empty_new_build"),
        source("ddddddddddd"),
        source("eeeeeeeeeee"),
        source("fffffffffff"),
        source("ggggggggggg"),
    ]
    decisions = [keep_decision(s.video_id) for s in sources[:6]]
    decisions.append(keep_decision("ggggggggggg", keep=False))
    done = {
        "ddddddddddd": record("ddddddddddd", "skip"),
        "eeeeeeeeeee": record("eeeeeeeeeee", "failed"),
        "fffffffffff": record("fffffffffff", "keep", version="screen-v0"),
    }
    plan = plan_screening(sources, decisions, done, limit=10)
    assert [s.video_id for s in plan] == [
        "ccccccccccc",  # priority category
        "bbbbbbbbbbb",  # Creative Commons
        "aaaaaaaaaaa",
        "eeeeeeeeeee",  # failed: retried
        "fffffffffff",  # older screen version: redone
    ]
    assert len(plan_screening(sources, decisions, done, limit=2)) == 2


def test_build_request_clips_only_long_videos() -> None:
    short = build_request(source("aaaaaaaaaaa", duration_s=300)).payload
    assert short["end_s"] == 300 and not short["clip"]
    assert "00:00 and 05:00" in short["prompt"]
    long = build_request(source("aaaaaaaaaaa", duration_s=5000)).payload
    assert long["end_s"] == MAX_WINDOW_S and long["clip"]
    unknown = build_request(source("aaaaaaaaaaa", duration_s=None)).payload
    assert unknown["end_s"] == MAX_WINDOW_S and unknown["clip"]


# Vertex provider


class Tokens:
    def token(self) -> str:
        return TOKEN


def vertex(handler: Any, model: str = GEMINI_3_FLASH) -> VertexGeminiProvider:
    return VertexGeminiProvider(
        "g",
        model,
        project="proj",
        tokens=Tokens(),
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


def vertex_reply(output: Any, usage: Mapping[str, int], finish: str = "STOP") -> httpx.Response:
    text = output if isinstance(output, str) else json.dumps(output)
    return httpx.Response(
        200,
        json={
            "candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": finish}],
            "usageMetadata": usage,
        },
    )


USAGE = {"promptTokenCount": 70_205, "candidatesTokenCount": 640, "thoughtsTokenCount": 100}


async def test_vertex_provider_sends_the_video_and_charges_measured_usage() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return vertex_reply(answer(), USAGE)

    provider = vertex(handler)
    req = build_request(source("aaaaaaaaaaa", duration_s=767))
    result = await provider.call(req)

    assert result.output == answer()
    url = str(seen[0].url)
    assert url.startswith("https://aiplatform.googleapis.com/v1/projects/proj/locations/global/")
    assert url.endswith(f"/models/{GEMINI_3_FLASH}:generateContent")
    assert seen[0].headers["Authorization"] == f"Bearer {TOKEN}"
    body = json.loads(seen[0].content)
    part = body["contents"][0]["parts"][0]
    assert part["fileData"]["fileUri"] == "https://www.youtube.com/watch?v=aaaaaaaaaaa"
    assert part["videoMetadata"] == {"fps": 1.0}  # whole video: no offsets
    assert body["generationConfig"]["mediaResolution"] == "MEDIA_RESOLUTION_LOW"
    # 70,205 in at $0.50/M plus 740 out at $3/M, at 88 rupees per dollar.
    assert result.cost_micro_inr == 3_284_380
    assert provider.billed_micro_inr == result.cost_micro_inr
    # The estimate is an upper bound on what the pilot measured.
    assert provider.estimate_cost_micro_inr(req) >= result.cost_micro_inr


async def test_vertex_provider_sends_offsets_when_clipping() -> None:
    bodies: list[Any] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return vertex_reply(answer(), USAGE)

    await vertex(handler).call(build_request(source("aaaaaaaaaaa", duration_s=5000)))
    meta = bodies[0]["contents"][0]["parts"][0]["videoMetadata"]
    assert meta == {"fps": 1.0, "startOffset": "0s", "endOffset": "1200s"}


async def test_vertex_provider_bills_a_truncated_answer_and_rejects_it() -> None:
    provider = vertex(lambda r: vertex_reply('{"keep": tr', USAGE, finish="MAX_TOKENS"))
    with pytest.raises(InvalidOutputError, match="MAX_TOKENS"):
        await provider.call(build_request(source("aaaaaaaaaaa")))
    assert provider.billed_micro_inr > 0


@pytest.mark.parametrize(("status", "retryable"), [(429, True), (503, True), (401, False)])
async def test_vertex_provider_errors_never_carry_the_token_or_url(
    status: int, retryable: bool
) -> None:
    provider = vertex(lambda r: httpx.Response(status, json={"error": {"message": TOKEN}}))
    with pytest.raises(ProviderError) as caught:
        await provider.call(build_request(source("aaaaaaaaaaa")))
    assert caught.value.retryable is retryable
    message = str(caught.value)
    assert TOKEN not in message and "googleapis" not in message and "proj" not in message
    assert provider.billed_micro_inr == 0


async def test_vertex_provider_hides_credential_errors() -> None:
    class Broken:
        def token(self) -> str:
            raise RuntimeError(f"bad key {TOKEN}")

    provider = VertexGeminiProvider("g", GEMINI_3_FLASH, project="p", tokens=Broken())
    with pytest.raises(ProviderError) as caught:
        await provider.call(build_request(source("aaaaaaaaaaa")))
    assert TOKEN not in str(caught.value)
    assert caught.value.retryable is False


def test_vertex_provider_needs_a_pinned_price() -> None:
    with pytest.raises(ValueError, match="No pinned price"):
        VertexGeminiProvider("g", "gemini-unknown", project="p", tokens=Tokens())


def test_parse_service_account_accepts_json_or_base64_and_never_echoes() -> None:
    info = {"type": "service_account", "private_key": "SECRET-VALUE"}
    raw = json.dumps(info)
    assert parse_service_account(raw) == info
    assert parse_service_account(base64.b64encode(raw.encode()).decode()) == info
    for bad in ("SECRET-VALUE not json", json.dumps({"type": "user", "k": "SECRET-VALUE"})):
        with pytest.raises(ValueError) as caught:
            parse_service_account(bad)
        assert "SECRET-VALUE" not in str(caught.value)


# The whole run, through the gateway


class Scripted:
    """A provider that answers from a script, one entry per call."""

    modalities: frozenset[Modality] = frozenset({"vision"})
    max_concurrency = 4

    def __init__(self, name: str, script: list[Any], cost: int = 1_000_000) -> None:
        self.name = name
        self.model = name + "@1"
        self.script = script
        self.cost = cost
        self.billed_micro_inr = 0

    def estimate_cost_micro_inr(self, request: ModelRequest) -> int:
        return self.cost

    async def call(self, request: ModelRequest) -> ProviderResult:
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        self.billed_micro_inr += self.cost
        return ProviderResult(output=item, cost_micro_inr=self.cost)


async def no_sleep(_: float) -> None:
    return None


def gateway(*chain: Scripted) -> ModelGateway:
    return ModelGateway(
        list(chain),
        ledger=InMemorySpendLedger(SpendCaps(10**12, 10**12)),
        call_log=InMemoryCallLog(),
        retry=RetryPolicy(max_attempts=2),
        sleep=no_sleep,
    )


async def test_screen_all_falls_back_records_and_exports_segments(tmp_path: Path) -> None:
    drift = answer(segments=[("kitchen", "09:00", "15:00")])  # past a 600 s video
    primary = Scripted(
        "primary",
        [
            answer(segments=[("kitchen", "00:10", "00:40"), ("bedroom", "01:00", "01:03")]),
            answer(keep=False),
            drift,
            drift,
            drift,
            drift,
        ],
    )
    fallback = Scripted(
        "fallback", [answer(segments=[("bathroom", "02:00", "02:30")]), drift, drift]
    )
    ledger = tmp_path / "screening.jsonl"
    sources = [
        source("aaaaaaaaaaa"),
        source("bbbbbbbbbbb"),
        source("ccccccccccc"),
        source("ddddddddddd"),
    ]

    def billed() -> int:
        return primary.billed_micro_inr + fallback.billed_micro_inr

    summary = await screen_all(
        sources,
        gateway=gateway(primary, fallback),
        ledger_path=ledger,
        billed_micro_inr=billed,
        cap_micro_inr=10**12,
        max_call_micro_inr=1,
        concurrency=1,
        now=lambda: NOW,
    )

    assert (summary.kept, summary.skipped, summary.failed) == (2, 1, 1)
    screened = read_screening(ledger)
    a = screened["aaaaaaaaaaa"]
    assert a.status == "keep" and a.model == "primary@1"
    assert [(s.room_type, s.start_s, s.end_s) for s in a.segments] == [("kitchen", 10, 40)]
    assert screened["bbbbbbbbbbb"].status == "skip"
    c = screened["ccccccccccc"]
    assert c.status == "keep" and c.model == "fallback@1"  # primary drifted twice
    assert screened["ddddddddddd"].status == "failed"
    assert all(r.use == "internal_training_only" for r in screened.values())

    segments = kept_segments(sources, screened)
    assert [(s.video_id, s.room_type, s.origin) for s in segments] == [
        ("aaaaaaaaaaa", "kitchen", "screening"),
        ("ccccccccccc", "bathroom", "screening"),
    ]


async def test_screen_all_stops_before_the_cap(tmp_path: Path) -> None:
    primary = Scripted("primary", [answer() for _ in range(10)], cost=3)

    summary = await screen_all(
        [source(f"{c * 11}") for c in "abcdefghij"],
        gateway=gateway(primary),
        ledger_path=tmp_path / "s.jsonl",
        billed_micro_inr=lambda: primary.billed_micro_inr,
        cap_micro_inr=10,
        max_call_micro_inr=3,
        concurrency=1,
    )
    assert summary.kept == 3  # 9 billed; a fourth worst-case call would pass 10
    assert summary.stopped_at_cap


def test_cli_screen_needs_a_project(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("GCP_PROJECT_ID", raising=False)
    with pytest.raises(SystemExit, match="GCP_PROJECT_ID"):
        main(["screen", "--manifest", str(tmp_path / "m.jsonl")])


def test_chain_models_are_priced() -> None:
    assert {GEMINI_3_FLASH, GEMINI_35_FLASH_LITE} <= {
        VertexGeminiProvider("a", m, project="p", tokens=Tokens()).model
        for m in (GEMINI_3_FLASH, GEMINI_35_FLASH_LITE)
    }
