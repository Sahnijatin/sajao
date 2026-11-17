"""Runs the eval-set stages through the model gateway (see `evalset`).

Every stage reads and appends JSON-lines files in one folder, skips frames it has
already done, and stops cleanly at a spend cap. Claude and Gemini spend each go to
a monthly ledger in that folder; Claude's cap is hard.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from sajao_dataset.evalset import (
    CHECK_PROMPT_ID,
    CHECK_SCHEMA,
    LABEL_PROMPT,
    LABEL_PROMPT_ID,
    LABEL_SCHEMA,
    TAG_PROMPT,
    TAG_PROMPT_ID,
    TAG_SCHEMA,
    BilledProvider,
    MonthlySpendLedger,
    append_jsonl,
    check_labels,
    check_prompt,
    check_review_for,
    check_tag,
    read_jsonl,
)
from sajao_gateway import (
    MICRO_INR_PER_RUPEE,
    AllProvidersFailedError,
    ModelGateway,
    ModelRequest,
    RetryPolicy,
    SpendCapExceededError,
)

INR_PER_USD = 95  # As the workers' vision prices.
CLAUDE_MONTHLY_CAP_USD = 20.0
GEMINI_MONTHLY_CAP_INR = 1000.0

TAG_LONG_SIDE = 768
LONG_SIDE = 1024  # As the listing step.
RETRY = RetryPolicy(max_attempts=2, timeout_seconds=300.0)


def jpeg(path: Path, long_side: int, boxes: Sequence[Mapping[str, Any]] = ()) -> bytes:
    """The frame as JPEG, at most `long_side` px, with numbered boxes drawn if given."""
    image = cv2.imread(str(path))
    if image is None:
        raise FileNotFoundError(path)
    h, w = image.shape[:2]
    scale = min(1.0, long_side / max(h, w))
    if scale < 1.0:
        image = cv2.resize(
            image, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA
        )
    h, w = image.shape[:2]
    for i, o in enumerate(boxes, start=1):
        y0, x0, y1, x1 = (int(v) for v in o["box_2d"])
        p0 = (round(x0 * w / 1000), round(y0 * h / 1000))
        p1 = (round(x1 * w / 1000), round(y1 * h / 1000))
        cv2.rectangle(image, p0, p1, (0, 255, 255), 2)
        label = str(i)
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
        cv2.rectangle(image, p0, (p0[0] + tw + 6, p0[1] + th + 8), (0, 0, 0), -1)
        cv2.putText(
            image,
            label,
            (p0[0] + 3, p0[1] + th + 3),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 255),
            2,
        )
    ok, data = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not ok:
        raise ValueError(f"could not encode {path}")
    return bytes(np.asarray(data).tobytes())


@dataclass
class Models:
    """The gateways, and the two monthly ledgers they charge."""

    tagger: ModelGateway
    labeller: ModelGateway
    checker: ModelGateway
    lister: ModelGateway
    claude: MonthlySpendLedger
    gemini: MonthlySpendLedger


def build_models(folder: Path, *, claude_cap_usd: float = CLAUDE_MONTHLY_CAP_USD) -> Models:
    import anthropic

    from sajao_workers.vision import (
        CLAUDE_OPUS,
        GEMINI_3_FLASH,
        GEMINI_35_FLASH_LITE,
        ClaudeVision,
        GoogleTokens,
        VertexGeminiVision,
    )

    claude = MonthlySpendLedger(
        folder / "claude_spend.jsonl", int(claude_cap_usd * INR_PER_USD * MICRO_INR_PER_RUPEE)
    )
    gemini = MonthlySpendLedger(
        folder / "gemini_spend.jsonl", int(GEMINI_MONTHLY_CAP_INR * MICRO_INR_PER_RUPEE)
    )
    from sajao_dataset.screen import FileCallLog

    calls = FileCallLog(folder / "calls.jsonl")
    tokens = GoogleTokens()
    project = os.environ["GCP_PROJECT_ID"]

    def vertex(name: str, model: str) -> BilledProvider:
        return BilledProvider(
            VertexGeminiVision(name, model, project=project, tokens=tokens), gemini
        )

    key = os.environ.get("SAJAO_ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    client = anthropic.AsyncAnthropic(api_key=key, max_retries=0)
    opus = BilledProvider(ClaudeVision("claude", CLAUDE_OPUS, client=client), claude)

    def gateway(chain: Sequence[Any], ledger: MonthlySpendLedger) -> ModelGateway:
        return ModelGateway(chain, ledger=ledger, retry=RETRY, call_log=calls)

    flash = vertex("gemini-flash", GEMINI_3_FLASH)
    lite = vertex("gemini-flash-lite", GEMINI_35_FLASH_LITE)
    return Models(
        tagger=gateway([lite, flash], gemini),
        labeller=gateway([flash, lite], gemini),
        checker=gateway([opus], claude),
        # The listing step's own chains (gpu/app.py): Gemini lists, Claude cross-checks.
        lister=gateway([flash, lite], gemini),
        claude=claude,
        gemini=gemini,
    )


@dataclass
class StageResult:
    done: int = 0
    skipped: int = 0
    failed: int = 0
    capped: bool = False
    by_model: dict[str, int] = field(default_factory=dict)


async def run_stage(
    frames: Sequence[Mapping[str, Any]],
    out_path: Path,
    work: Callable[[Mapping[str, Any]], Awaitable[dict[str, Any]]],
    *,
    key: str = "path",
    concurrency: int = 4,
) -> StageResult:
    """Run `work` on every frame not yet in `out_path`, appending each result."""
    done = {r[key] for r in read_jsonl(out_path)}
    todo = [f for f in frames if f[key] not in done]
    result = StageResult(skipped=len(frames) - len(todo))
    stop = asyncio.Event()
    gate = asyncio.Semaphore(concurrency)

    async def one(frame: Mapping[str, Any]) -> None:
        async with gate:
            if stop.is_set():
                return
            try:
                row = await work(frame)
            except SpendCapExceededError:
                result.capped = True
                stop.set()
                return
            except AllProvidersFailedError:
                result.failed += 1
                return
            append_jsonl(out_path, {key: frame[key], **row})
            result.done += 1
            model = str(row.get("model", ""))
            result.by_model[model] = result.by_model.get(model, 0) + 1

    await asyncio.gather(*(one(f) for f in todo))
    return result


def _payload(
    prompt: str, schema: Mapping[str, Any], max_tokens: int, thinking: str | None = None
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "prompt": prompt,
        "response_schema": dict(schema),
        "max_output_tokens": max_tokens,
    }
    if thinking:
        payload["thinking_level"] = thinking  # Gemini only; Claude ignores it
    return payload


def tag_work(
    models: Models, frames_dir: Path
) -> Callable[[Mapping[str, Any]], Awaitable[dict[str, Any]]]:
    async def work(frame: Mapping[str, Any]) -> dict[str, Any]:
        request = ModelRequest(
            "evalset_tag",
            "vision",
            TAG_PROMPT_ID,
            _payload(TAG_PROMPT, TAG_SCHEMA, 2048, "low"),
            (jpeg(frames_dir / frame["path"], TAG_LONG_SIDE),),
        )
        response = await models.tagger.call(request, validate=check_tag)
        meta = {k: frame[k] for k in ("video_id", "clip_path", "room_type", "t_s")}
        return {**meta, "present": sorted(set(response.output["present"])), "model": response.model}

    return work


def label_work(
    models: Models, frames_dir: Path
) -> Callable[[Mapping[str, Any]], Awaitable[dict[str, Any]]]:
    async def work(frame: Mapping[str, Any]) -> dict[str, Any]:
        request = ModelRequest(
            "evalset_label",
            "vision",
            LABEL_PROMPT_ID,
            _payload(LABEL_PROMPT, LABEL_SCHEMA, 8192, "low"),
            (jpeg(frames_dir / frame["path"], LONG_SIDE),),
        )
        response = await models.labeller.call(request, validate=check_labels)
        objects = [{"class": o["class"], "box_2d": o["box_2d"]} for o in response.output["objects"]]
        return {"objects": objects, "model": response.model}

    return work


def check_work(
    models: Models, frames_dir: Path, labels: Mapping[str, Sequence[Mapping[str, Any]]]
) -> Callable[[Mapping[str, Any]], Awaitable[dict[str, Any]]]:
    async def work(frame: Mapping[str, Any]) -> dict[str, Any]:
        objects = labels[frame["path"]]
        request = ModelRequest(
            "evalset_check",
            "vision",
            CHECK_PROMPT_ID,
            _payload(check_prompt(objects), CHECK_SCHEMA, 6000),
            (jpeg(frames_dir / frame["path"], LONG_SIDE, objects),),
        )
        response = await models.checker.call(request, validate=check_review_for(len(objects)))
        return {
            "reviews": sorted(response.output["reviews"], key=lambda r: int(r["id"])),
            "missed": response.output["missed"],
            "model": response.model,
        }

    return work


def listing_work(
    models: Models, frames_dir: Path, role: str
) -> Callable[[Mapping[str, Any]], Awaitable[dict[str, Any]]]:
    """The listing step's own request (prompt, schema, image size) on one frame."""
    from sajao_workers.models import INVENTORY_MAX_TOKENS, INVENTORY_PROMPT, INVENTORY_PROMPT_ID
    from sajao_workers.twin.inventory import INVENTORY_SCHEMA, check_inventory

    gateway = models.lister if role == "list" else models.checker

    async def work(frame: Mapping[str, Any]) -> dict[str, Any]:
        request = ModelRequest(
            "evalset_listing",
            "vision",
            INVENTORY_PROMPT_ID,
            _payload(INVENTORY_PROMPT, INVENTORY_SCHEMA, INVENTORY_MAX_TOKENS),
            (jpeg(frames_dir / frame["path"], LONG_SIDE),),
        )
        response = await gateway.call(request, validate=check_inventory)
        return {"items": response.output["items"], "model": response.model}

    return work


def spend_line(models: Models) -> str:
    def usd(micro: int) -> float:
        return micro / MICRO_INR_PER_RUPEE / INR_PER_USD

    return (
        f"this month: Claude USD {usd(models.claude.spent()):.2f} of {usd(models.claude.cap):.0f},"
        f" Gemini USD {usd(models.gemini.spent()):.2f}"
    )


# --- Hand-check export and scoring ------------------------------------------


def export_handcheck(
    folder: Path, frames_dir: Path, selected: Sequence[Mapping[str, Any]]
) -> tuple[int, int]:
    """Write `handcheck.jsonl` (one row per disagreement, `decision` empty) and an
    overlay per frame in `handcheck/`: the disputed boxes in red, numbered as in the
    sheet, and the agreed labels in green. Returns (frames, rows)."""
    from sajao_dataset.evalset import disagreements

    labels = {r["path"]: r["objects"] for r in read_jsonl(folder / "labels.jsonl")}
    reviews = {r["path"]: r for r in read_jsonl(folder / "reviews.jsonl")}
    out_dir = folder / "handcheck"
    out_dir.mkdir(parents=True, exist_ok=True)
    sheet = folder / "handcheck.jsonl"
    sheet.unlink(missing_ok=True)
    frames = rows = 0
    for f in selected:
        path = f["path"]
        if path not in labels or path not in reviews:
            continue
        items = disagreements(labels[path], reviews[path])
        if not items:
            continue
        frames += 1
        verdict = {int(r["id"]): r["verdict"] for r in reviews[path]["reviews"]}
        agreed = [o for i, o in enumerate(labels[path], start=1) if verdict[i] == "agree"]
        image_name = path.replace("/", "__")
        _overlay(frames_dir / path, out_dir / image_name, items, agreed)
        for n, item in enumerate(items, start=1):
            rows += 1
            append_jsonl(
                sheet,
                {
                    "key": f"{path}#{item['item']}",
                    "path": path,
                    "image": f"handcheck/{image_name}",
                    "number": n,
                    "room_type": f["room_type"],
                    **item,
                    "decision": None,  # keep, drop or relabel (with "class")
                },
            )
    return frames, rows


def _overlay(
    src: Path,
    dst: Path,
    disputed: Sequence[Mapping[str, Any]],
    agreed: Sequence[Mapping[str, Any]],
) -> None:
    image = cv2.imread(str(src))
    if image is None:
        raise FileNotFoundError(src)
    h, w = image.shape[:2]

    def draw(box: Sequence[int], colour: tuple[int, int, int], text: str) -> None:
        y0, x0, y1, x1 = (int(v) for v in box)
        p0 = (round(x0 * w / 1000), round(y0 * h / 1000))
        p1 = (round(x1 * w / 1000), round(y1 * h / 1000))
        cv2.rectangle(image, p0, p1, colour, 3)
        (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)
        cv2.rectangle(image, p0, (p0[0] + tw + 8, p0[1] + th + 10), colour, -1)
        cv2.putText(
            image, text, (p0[0] + 4, p0[1] + th + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2
        )

    for o in agreed:
        draw(o["box_2d"], (90, 200, 90), str(o["class"]))
    for n, item in enumerate(disputed, start=1):
        draw(item["box_2d"], (60, 60, 230), f"{n} {item['class']}")
    cv2.imwrite(str(dst), image, [cv2.IMWRITE_JPEG_QUALITY, 88])


def score(folder: Path, selected: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Per-class listing scores against the eval labels. Hand-check decisions are
    used where present; unresolved disagreements are left out of the truth."""
    from sajao_dataset.evalset import final_objects, listed_classes, score_listing

    labels = {r["path"]: r["objects"] for r in read_jsonl(folder / "labels.jsonl")}
    reviews = {r["path"]: r for r in read_jsonl(folder / "reviews.jsonl")}
    decisions: dict[str, dict[str, Any]] = {}
    for row in read_jsonl(folder / "decisions.jsonl"):
        decisions.setdefault(row["path"], {})[row["item"]] = row
    truth: dict[str, set[str]] = {}
    unresolved = 0
    for f in selected:
        path = f["path"]
        if path in labels and path in reviews:
            objects, open_items = final_objects(labels[path], reviews[path], decisions.get(path))
            truth[path] = {o["class"] for o in objects}
            unresolved += open_items
    listed: dict[str, dict[str, set[str]]] = {}
    unmatched: dict[str, int] = {}
    for role in ("list", "cross_check"):
        rows = read_jsonl(folder / f"listing_{role}.jsonl")
        listed[role] = {}
        for r in rows:
            found, other = listed_classes(r["items"])
            listed[role][r["path"]] = found
            for name in other:
                unmatched[name] = unmatched.get(name, 0) + 1
    both = set(listed["list"]) & set(listed["cross_check"])
    listed["merged"] = {p: listed["list"][p] | listed["cross_check"][p] for p in both}
    return {
        "version": "evalset-v1",
        "frames": len(truth),
        "unresolved_disagreements": unresolved,
        "per_class": {role: score_listing(truth, rows) for role, rows in listed.items()},
        "top_unmatched_names": sorted(unmatched.items(), key=lambda kv: -kv[1])[:40],
    }
