"""Screen candidate videos with Gemini: keep or skip, and room segments.

Gemini reads each public YouTube URL directly through the model gateway, so
nothing is downloaded. Each answer is validated (room type in the pinned list,
segments ordered and inside the screened window, keep has segments and skip has
none); an invalid answer is rejected and the next model in the chain is tried.
Every result is appended to a ledger, so reruns skip videos already screened
with this `SCREEN_VERSION`, and failed videos are retried.

Labels are room types and time ranges only. No model sets a dimension, position
or price.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from sajao_dataset.download import Segment
from sajao_dataset.gemini import (
    GEMINI_3_FLASH,
    GEMINI_35_FLASH_LITE,
    GoogleTokens,
    TokenSource,
    VertexGeminiProvider,
)
from sajao_dataset.manifest import SourceRecord
from sajao_dataset.prefilter import Decision
from sajao_dataset.youtube import rank
from sajao_gateway import (
    MICRO_INR_PER_RUPEE,
    AllProvidersFailedError,
    CallRecord,
    InMemorySpendLedger,
    InvalidOutputError,
    ModelGateway,
    ModelRequest,
    ProviderResult,
    RetryPolicy,
    SpendCapExceededError,
    SpendCaps,
)

SCREEN_VERSION = "screen-v1"
PROMPT_ID = "dataset_screen@1"

# Only the first 20 minutes of a video are screened: tours rarely show new rooms
# after that, and it caps the cost of one call.
MAX_WINDOW_S = 1200
FPS = 1.0
# Timestamps are asked for as MM:SS. Asked for plain seconds, both models stretched
# the timeline 1.4 to 1.6 times past the end of the video in the pilot; with MM:SS no
# segment fell outside the video and the two models agreed on its end within a second.
TIMESTAMP = re.compile(r"^(?:(\d{1,2}):)?(\d{1,3}):([0-5]\d)$")
MAX_OUTPUT_TOKENS = 8192  # 4096 ran out once on a 24-segment tour.
MIN_SEGMENT_S = 5.0
# Segment ends up to this far past the window are clamped, not rejected.
END_TOLERANCE_S = 2.0
MERGE_GAP_S = 2.0

RoomType = Literal[
    "living_room",
    "bedroom",
    "kitchen",
    "dining",
    "bathroom",
    "balcony",
    "puja_room",
    "study",
    "kids_room",
    "entrance",
    "utility",
    "corridor",
    "other_indoor",
]
ROOM_TYPES: tuple[str, ...] = RoomType.__args__  # type: ignore[attr-defined]

PROMPT = """\
You screen YouTube home tour videos for a dataset of real Indian home interiors used to \
train an object detector.

Keep the video only if it shows the inside of a real, lived-in or ready-to-move-in Indian \
home (flat, apartment, villa or independent house) filmed by a person walking through it. \
Skip it if it is mainly a builder sample flat or show flat, a 3D render or walkthrough \
animation, an interior designer's showcase reel, a slideshow of still photos, mostly \
exteriors, amenities or the presenter talking, or not in India. Judge India from what you \
see and hear (language, fittings, switches, signage); if you cannot tell, skip it.

If you keep it, list every continuous stretch where one indoor room is clearly visible, \
with its room type, start and end as MM:SS timestamps, and whether the room is furnished. \
Merge back-to-back shots of the same room. Leave out stretches shorter than 5 seconds, title \
cards, exterior and lift lobby shots, and moments when a person's face fills the frame. \
Every start and end must be between 00:00 and {end}. If you skip it, return no segments.

Give a short reason (under 20 words) for keep or skip."""

RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "keep": {"type": "BOOLEAN"},
        "reason": {"type": "STRING"},
        "segments": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "room_type": {"type": "STRING", "enum": list(ROOM_TYPES)},
                    "start": {"type": "STRING", "description": "MM:SS"},
                    "end": {"type": "STRING", "description": "MM:SS"},
                    "furnished": {"type": "BOOLEAN"},
                },
                "required": ["room_type", "start", "end", "furnished"],
            },
        },
    },
    "required": ["keep", "reason", "segments"],
}


class RoomSegment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    room_type: RoomType
    start_s: float = Field(ge=0)
    end_s: float
    furnished: bool


class RawSegment(BaseModel):
    """A segment as the model writes it, with MM:SS timestamps."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    room_type: RoomType
    start: str
    end: str
    furnished: bool


class RawOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    keep: bool
    reason: str = Field(min_length=1, max_length=300)
    segments: list[RawSegment]


class ScreenOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    keep: bool
    reason: str
    segments: list[RoomSegment]


def seconds(timestamp: str) -> float:
    """MM:SS or H:MM:SS to seconds. Raises ValueError for anything else."""
    match = TIMESTAMP.match(timestamp.strip())
    if match is None:
        raise ValueError("not an MM:SS timestamp")
    hours, minutes, secs = match.groups()
    return int(hours or 0) * 3600 + int(minutes) * 60 + int(secs)


def mmss(value: float) -> str:
    whole = int(value)
    return f"{whole // 60:02d}:{whole % 60:02d}"


def parse_output(output: Any, window_s: float) -> ScreenOutput:
    """Validate a model answer. Raises InvalidOutputError when it cannot be trusted.

    Ends slightly past the window are clamped; anything further means the model
    lost track of the timeline, so the whole answer is rejected.
    """
    try:
        raw = RawOutput.model_validate(output)
        parsed = ScreenOutput(
            keep=raw.keep,
            reason=raw.reason,
            segments=[
                RoomSegment(
                    room_type=r.room_type,
                    start_s=seconds(r.start),
                    end_s=seconds(r.end),
                    furnished=r.furnished,
                )
                for r in raw.segments
            ],
        )
    except ValidationError as error:
        raise InvalidOutputError(f"schema: {error.error_count()} errors") from None
    except ValueError:
        raise InvalidOutputError("a timestamp is not MM:SS") from None
    if parsed.keep and not parsed.segments:
        raise InvalidOutputError("keep without segments")
    if not parsed.keep and parsed.segments:
        raise InvalidOutputError("skip with segments")
    clamped = []
    for s in parsed.segments:
        if s.end_s <= s.start_s:
            raise InvalidOutputError("segment ends before it starts")
        if s.end_s > window_s + END_TOLERANCE_S:
            raise InvalidOutputError("segment past the end of the screened window")
        clamped.append(s.model_copy(update={"end_s": min(s.end_s, window_s)}))
    return parsed.model_copy(update={"segments": clamped})


def tidy_segments(segments: Sequence[RoomSegment]) -> list[RoomSegment]:
    """Sort, merge same-room segments that touch or overlap, drop short ones."""
    merged: list[RoomSegment] = []
    for s in sorted(segments, key=lambda s: (s.start_s, s.end_s)):
        last = merged[-1] if merged else None
        if (
            last is not None
            and last.room_type == s.room_type
            and s.start_s <= last.end_s + MERGE_GAP_S
        ):
            merged[-1] = last.model_copy(
                update={
                    "end_s": max(last.end_s, s.end_s),
                    "furnished": last.furnished or s.furnished,
                }
            )
        else:
            merged.append(s)
    return [s for s in merged if s.end_s - s.start_s >= MIN_SEGMENT_S]


Status = Literal["keep", "skip", "failed"]


class ScreenRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    video_id: str = Field(pattern=r"^[A-Za-z0-9_-]{11}$")
    screen_version: str
    prompt_id: str
    status: Status
    reason: str | None
    segments: list[RoomSegment]
    window_s: float
    provider: str | None
    model: str | None
    cost_micro_inr: int
    """What the answering call cost. Rejected attempts are in the run total only."""
    screened_at: datetime
    use: Literal["internal_training_only"] = "internal_training_only"


def read_screening(path: Path) -> dict[str, ScreenRecord]:
    """Latest record per video wins."""
    if not path.exists():
        return {}
    latest: dict[str, ScreenRecord] = {}
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                record = ScreenRecord.model_validate_json(line)
                latest[record.video_id] = record
    return latest


def append_screening(path: Path, record: ScreenRecord) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(record.model_dump_json() + "\n")


def plan_screening(
    sources: Iterable[SourceRecord],
    decisions: Iterable[Decision],
    done: dict[str, ScreenRecord],
    *,
    limit: int,
) -> list[SourceRecord]:
    """Videos the pre-filter kept that this screen version has not answered yet,
    priority category first, then Creative Commons first."""
    keep = {d.video_id for d in decisions if d.keep}
    todo = [
        s
        for s in sources
        if s.video_id in keep
        and not (
            (r := done.get(s.video_id)) is not None
            and r.screen_version == SCREEN_VERSION
            and r.status != "failed"
        )
    ]
    todo.sort(key=rank)
    return todo[:limit]


def window_of(source: SourceRecord) -> float:
    return float(min(source.duration_s or MAX_WINDOW_S, MAX_WINDOW_S))


def build_request(source: SourceRecord) -> ModelRequest:
    window = window_of(source)
    return ModelRequest(
        task="dataset_screen",
        modality="vision",
        prompt_id=PROMPT_ID,
        payload={
            "video_url": str(source.url),
            "start_s": 0,
            "end_s": window,
            "clip": source.duration_s is None or source.duration_s > MAX_WINDOW_S,
            "fps": FPS,
            "prompt": PROMPT.format(end=mmss(window)),
            "response_schema": RESPONSE_SCHEMA,
            "max_output_tokens": MAX_OUTPUT_TOKENS,
        },
    )


@dataclass
class ScreenSummary:
    kept: int = 0
    skipped: int = 0
    failed: int = 0
    by_model: dict[str, int] = field(default_factory=dict)
    stopped_at_cap: bool = False


async def screen_all(
    sources: Sequence[SourceRecord],
    *,
    gateway: ModelGateway,
    ledger_path: Path,
    billed_micro_inr: Callable[[], int],
    cap_micro_inr: int,
    max_call_micro_inr: int,
    concurrency: int = 4,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> ScreenSummary:
    """Screen each video once. Stops starting new videos when the billed spend
    plus one worst-case call would pass the run cap."""
    summary = ScreenSummary()
    gate = asyncio.Semaphore(concurrency)
    in_flight = 0

    async def one(source: SourceRecord) -> None:
        nonlocal in_flight
        async with gate:
            if billed_micro_inr() + (in_flight + 1) * max_call_micro_inr > cap_micro_inr:
                summary.stopped_at_cap = True
                return
            in_flight += 1
            try:
                record = await _screen_one(gateway, source, now)
            finally:
                in_flight -= 1
        if record is None:
            summary.stopped_at_cap = True
            return
        append_screening(ledger_path, record)
        if record.status == "keep":
            summary.kept += 1
        elif record.status == "skip":
            summary.skipped += 1
        else:
            summary.failed += 1
        if record.model:
            summary.by_model[record.model] = summary.by_model.get(record.model, 0) + 1

    await asyncio.gather(*(one(s) for s in sources))
    return summary


async def _screen_one(
    gateway: ModelGateway, source: SourceRecord, now: Callable[[], datetime]
) -> ScreenRecord | None:
    window = window_of(source)
    request = build_request(source)

    def validate(result: ProviderResult) -> None:
        parse_output(result.output, window)

    def record(
        status: Status, reason: str, segments: list[RoomSegment], **model: Any
    ) -> ScreenRecord:
        return ScreenRecord(
            video_id=source.video_id,
            screen_version=SCREEN_VERSION,
            prompt_id=PROMPT_ID,
            status=status,
            reason=reason,
            segments=segments,
            window_s=window,
            provider=model.get("provider"),
            model=model.get("model"),
            cost_micro_inr=model.get("cost_micro_inr", 0),
            screened_at=now(),
        )

    try:
        response = await gateway.call(request, validate=validate)
    except SpendCapExceededError:
        return None
    except AllProvidersFailedError:
        return record("failed", "no model returned a valid answer", [])
    parsed = parse_output(response.output, window)
    segments = tidy_segments(parsed.segments)
    status: Status = "keep" if parsed.keep and segments else "skip"
    return record(
        status,
        parsed.reason,
        segments if status == "keep" else [],
        provider=response.provider,
        model=response.model,
        cost_micro_inr=response.cost_micro_inr,
    )


def kept_segments(
    sources: Iterable[SourceRecord], screening: dict[str, ScreenRecord]
) -> list[Segment]:
    """Download segments for every kept video, in download priority order."""
    by_id = {s.video_id: s for s in sources}
    ordered = sorted(
        (r for r in screening.values() if r.status == "keep" and r.video_id in by_id),
        key=lambda r: rank(by_id[r.video_id]),
    )
    return [
        Segment(
            video_id=r.video_id,
            start_s=s.start_s,
            end_s=s.end_s,
            room_type=s.room_type,
            origin="screening",
        )
        for r in ordered
        for s in r.segments
    ]


def write_segments(path: Path, segments: Iterable[Segment]) -> int:
    """Rewritten from the ledger on every run."""
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for segment in segments:
            f.write(segment.model_dump_json() + "\n")
            count += 1
    return count


# A rejected answer is retried once on the same model before falling back.
RETRY = RetryPolicy(max_attempts=2, timeout_seconds=600.0)


def screening_chain(project: str, tokens: TokenSource) -> list[VertexGeminiProvider]:
    """Gemini 3 Flash kept its timestamps inside the video in the pilot; Gemini 3.5
    Flash-Lite is cheaper but drifted, so its answers are often rejected."""
    return [
        VertexGeminiProvider("gemini-3-flash", GEMINI_3_FLASH, project=project, tokens=tokens),
        VertexGeminiProvider(
            "gemini-3.5-flash-lite", GEMINI_35_FLASH_LITE, project=project, tokens=tokens
        ),
    ]


def worst_case_per_video_micro_inr(chain: Sequence[VertexGeminiProvider]) -> int:
    """Every attempt on every model in the chain, for a full-length window."""
    probe = build_request(
        SourceRecord.model_construct(video_id="x" * 11, url="https://youtu.be/x", duration_s=None)
    )
    return RETRY.max_attempts * sum(p.estimate_cost_micro_inr(probe) for p in chain)


class FileCallLog:
    """The gateway's call log as JSON lines in a file: hashes, outcomes, cost and
    latency, never prompts, outputs, URLs or credentials."""

    def __init__(self, path: Path) -> None:
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, entry: CallRecord) -> None:
        with self._path.open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(dataclasses.asdict(entry), sort_keys=True) + "\n")


@dataclass
class RunResult:
    summary: ScreenSummary
    billed_inr: float


async def run_screening(
    sources: Sequence[SourceRecord],
    *,
    project: str,
    ledger_path: Path,
    cap_inr: float,
    call_log_path: Path,
    concurrency: int = 2,
    tokens: TokenSource | None = None,
) -> RunResult:
    chain = screening_chain(project, tokens or GoogleTokens())
    cap = int(cap_inr * MICRO_INR_PER_RUPEE)
    gateway = ModelGateway(
        chain,
        ledger=InMemorySpendLedger(SpendCaps(cap, cap)),
        call_log=FileCallLog(call_log_path),
        retry=RETRY,
    )

    def billed() -> int:
        return sum(p.billed_micro_inr for p in chain)

    summary = await screen_all(
        sources,
        gateway=gateway,
        ledger_path=ledger_path,
        billed_micro_inr=billed,
        cap_micro_inr=cap,
        max_call_micro_inr=worst_case_per_video_micro_inr(chain),
        concurrency=concurrency,
    )
    return RunResult(summary, billed() / MICRO_INR_PER_RUPEE)
