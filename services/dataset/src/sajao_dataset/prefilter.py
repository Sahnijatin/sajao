"""Free keyword pre-filter that runs before Gemini screening.

Drops builder and designer promos (sample flats, show flats, builder
walkthroughs, designer reels, 3D renders) and anything under a minute. It is
pure and deterministic, so its output is a function of the manifest and the
pinned term list. Changing a term means a new version.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from sajao_dataset.manifest import SourceRecord

PREFILTER_VERSION = "promo-v1"
MIN_DURATION_S = 60

Field = Literal["title", "description", "channel"]

_TEXT_TERMS: dict[str, tuple[str, ...]] = {
    "sample_flat": (
        r"sample (flat|apartment|house|home|unit|villa)s?",
        r"model (flat|apartment|house|unit)s?",
    ),
    "show_flat": (r"show ?(flat|home|house|apartment|unit)s?",),
    "builder_walkthrough": (
        r"walk ?through by (the )?(builder|developer)",
        r"(builder|developer)'?s? walk ?through",
        r"(3d|virtual|project) walk ?through",
        r"new launch",
        r"pre[- ]?launch",
        r"\brera\b",
        r"site visit",
    ),
    "designer_reel": (
        r"interior design(er|ers)? (reel|portfolio|project|work)s?",
        r"interior designers? in \w+",
        r"#interiordesign\w*",
    ),
    "render_3d": (
        r"3d (render|rendering|renders|animation|visuali[sz]ation|view|model)",
        r"\brender(ed|ing|s)?\b",
        r"walkthrough animation",
    ),
    "sale_listing": (
        r"\bfor (sale|resale)\b",
        r"\b(flats?|rooms?|houses?|apartments?) for rent\b",
        r"loan up ?to",
        r"\bready to move\b",
        r"रजिस्ट्री",
    ),
    "shorts": (r"#shorts?\b",),
}

# Business names that only make sense in the channel field.
_CHANNEL_TERMS: dict[str, tuple[str, ...]] = {
    "builder_walkthrough": (
        r"\b(realty|realtors?|real ?estate|estates?|properties|builders|developers)\b",
        r"\bconstructions?\b",
        r"\bpvt\.? ?ltd\b",
        r"\bprop",
    ),
    "designer_reel": (r"interior", r"\bdecorators?\b"),
}


def _compile(terms: dict[str, tuple[str, ...]]) -> list[tuple[str, re.Pattern[str]]]:
    return [(reason, re.compile(p, re.IGNORECASE)) for reason, ps in terms.items() for p in ps]


_TEXT = _compile(_TEXT_TERMS)
_CHANNEL = _compile(_CHANNEL_TERMS)


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    video_id: str
    keep: bool
    reason: str | None
    field: Field | Literal["duration"] | None
    matched: str | None
    version: str = PREFILTER_VERSION


def decide(record: SourceRecord) -> Decision:
    if record.duration_s is not None and record.duration_s < MIN_DURATION_S:
        return Decision(
            video_id=record.video_id,
            keep=False,
            reason="too_short",
            field="duration",
            matched=str(record.duration_s),
        )
    fields: list[tuple[Field, str | None, list[tuple[str, re.Pattern[str]]]]] = [
        ("title", record.title, _TEXT),
        ("channel", record.channel, _TEXT + _CHANNEL),
        ("description", record.description, _TEXT),
    ]
    for field, text, patterns in fields:
        if not text:
            continue
        for reason, pattern in patterns:
            match = pattern.search(text)
            if match:
                return Decision(
                    video_id=record.video_id,
                    keep=False,
                    reason=reason,
                    field=field,
                    matched=match.group(0),
                )
    return Decision(video_id=record.video_id, keep=True, reason=None, field=None, matched=None)


def write_decisions(path: Path, decisions: Iterable[Decision]) -> None:
    """Rewrite the decisions file in full; the pre-filter is cheap and deterministic."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as f:
        for decision in decisions:
            f.write(decision.model_dump_json() + "\n")
    tmp.replace(path)


def read_decisions(path: Path) -> list[Decision]:
    with path.open(encoding="utf-8") as f:
        return [Decision.model_validate_json(line) for line in f if line.strip()]
