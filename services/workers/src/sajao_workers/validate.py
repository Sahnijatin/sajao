"""Validators for GPU model outputs. An output that fails is never used or cached.

Each builder takes the request payload and returns a gateway validator, so the
output is checked against exactly what was asked: same frames, same order,
classes from the vocabulary, boxes inside the image, one mask per box.
"""

import math
import re
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from sajao_gateway import InvalidOutputError, ProviderResult

DIGEST = re.compile(r"^[0-9a-f]{64}$")
Validator = Callable[[ProviderResult], None]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise InvalidOutputError(message)


def _unit(value: Any) -> bool:
    return isinstance(value, int | float) and math.isfinite(value) and 0.0 <= value <= 1.0


def _frames(result: ProviderResult, asked: Sequence[Mapping[str, Any]]) -> list[Any]:
    frames = result.output.get("frames")
    if not isinstance(frames, list) or len(frames) != len(asked):
        raise InvalidOutputError("one result per frame")
    for frame, image in zip(frames, asked, strict=True):
        _require(
            isinstance(frame, dict) and frame.get("image") == image["image"], "frames in order"
        )
    return frames


def check_detections(payload: Mapping[str, Any]) -> Validator:
    images: Sequence[Mapping[str, Any]] = payload["images"]
    vocabulary = set(payload["vocabulary"])

    def validate(result: ProviderResult) -> None:
        for frame, image in zip(_frames(result, images), images, strict=True):
            found = frame.get("detections")
            _require(isinstance(found, list), "detections is a list")
            for detection in found:
                _require(detection.get("label") in vocabulary, "label from the vocabulary")
                _require(_unit(detection.get("score")), "score between 0 and 1")
                _check_box(detection.get("box"), image["width"], image["height"])

    return validate


def _check_box(box: Any, width: int, height: int) -> None:
    _require(
        isinstance(box, list)
        and len(box) == 4
        and all(isinstance(v, int | float) and math.isfinite(v) for v in box),
        "box is four numbers",
    )
    x0, y0, x1, y1 = box
    _require(0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height, "box inside the image")


def check_masks(payload: Mapping[str, Any]) -> Validator:
    asked: Sequence[Mapping[str, Any]] = payload["frames"]

    def validate(result: ProviderResult) -> None:
        for frame, image in zip(_frames(result, asked), asked, strict=True):
            found = frame.get("masks")
            _require(
                isinstance(found, list) and len(found) == len(image["boxes"]), "one mask per box"
            )
            for mask in found:
                _require(DIGEST.match(str(mask.get("mask"))) is not None, "mask is a blob digest")
                area = mask.get("area")
                _require(
                    isinstance(area, int) and 0 < area <= image["width"] * image["height"],
                    "mask area inside the image",
                )
                _require(_unit(mask.get("score")), "score between 0 and 1")

    return validate
