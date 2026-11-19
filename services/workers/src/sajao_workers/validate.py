"""Validators for GPU model outputs. An output that fails is never used or cached.

Each builder takes the request payload and returns a gateway validator, so the
output is checked against exactly what was asked: same frames, same order,
classes from the vocabulary, boxes inside the image, one mask per box.
"""

import math
import re
from collections.abc import Callable, Mapping, Sequence
from typing import Any

import numpy as np

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


# Depth: most of each frame covered, and a median distance a room can have.
MIN_DEPTH_COVERAGE = 0.5
MIN_POSE_DEPTH_COVERAGE = 0.2
DEPTH_MEDIAN_RANGE_M = (0.3, 15.0)


# A field of view outside this (degrees, horizontal) is not a phone photo.
FOV_X_RANGE_DEG = (35.0, 120.0)


def _plausible_intrinsics(k: Any, frame: Mapping[str, Any]) -> bool:
    try:
        m = np.asarray(k, dtype=np.float64)
    except (TypeError, ValueError):
        return False
    if m.shape != (3, 3) or not np.isfinite(m).all() or min(m[0, 0], m[1, 1]) <= 0:
        return False
    w, h = float(frame["width"]), float(frame["height"])
    fov = math.degrees(2 * math.atan(w / (2 * m[0, 0])))
    return (
        FOV_X_RANGE_DEG[0] <= fov <= FOV_X_RANGE_DEG[1]
        and 0 < m[0, 2] < w
        and 0 < m[1, 2] < h
        and 0.8 <= m[0, 0] / m[1, 1] <= 1.25
    )


def check_depths(payload: Mapping[str, Any]) -> Validator:
    asked: Sequence[Mapping[str, Any]] = payload["frames"]

    def validate(result: ProviderResult) -> None:
        low, high = DEPTH_MEDIAN_RANGE_M
        for frame, asked_frame in zip(_frames(result, asked), asked, strict=True):
            _require(DIGEST.match(str(frame.get("depth"))) is not None, "depth is a blob digest")
            coverage = frame.get("coverage")
            _require(
                _unit(coverage) and coverage >= MIN_DEPTH_COVERAGE,
                f"depth covers at least {MIN_DEPTH_COVERAGE:.0%} of the frame",
            )
            median = frame.get("median_m")
            _require(
                isinstance(median, int | float) and math.isfinite(median) and low <= median <= high,
                "median depth is plausible for a room",
            )
            if "intrinsics" in asked_frame and asked_frame["intrinsics"] is None:
                _require(
                    _plausible_intrinsics(frame.get("intrinsics"), asked_frame),
                    "estimated intrinsics are a pinhole camera inside the image",
                )

    return validate


def check_poses(payload: Mapping[str, Any]) -> Validator:
    """A camera (a rotation and a position), intrinsics inside the image and a depth map
    for every photo asked, in order."""
    asked: Sequence[Mapping[str, Any]] = payload["frames"]

    def validate(result: ProviderResult) -> None:
        for frame in _frames(result, asked):
            c2w = frame.get("c2w")
            _require(
                isinstance(c2w, list)
                and len(c2w) == 4
                and all(isinstance(r, list) and len(r) == 4 for r in c2w)
                and all(isinstance(v, int | float) and math.isfinite(v) for r in c2w for v in r),
                "c2w is a finite 4 by 4 matrix",
            )
            rows = [r[:3] for r in c2w[:3]]
            for i in range(3):
                for j in range(3):
                    dot = sum(rows[k][i] * rows[k][j] for k in range(3))
                    _require(abs(dot - (1.0 if i == j else 0.0)) < 1e-2, "c2w turns, not stretches")
            k = frame.get("intrinsics")
            width, height = frame.get("width"), frame.get("height")
            _require(
                isinstance(width, int) and isinstance(height, int) and width > 0 and height > 0,
                "the photo's size",
            )
            _require(
                isinstance(k, list)
                and len(k) == 3
                and all(isinstance(v, int | float) and math.isfinite(v) for r in k for v in r)
                and k[0][0] > 0
                and k[1][1] > 0
                and 0 <= k[0][2] <= width
                and 0 <= k[1][2] <= height,
                "intrinsics with a focal length and a centre inside the photo",
            )
            _require(
                DIGEST.match(str(frame.get("pose_depth"))) is not None, "depth is a blob digest"
            )
            _require(_unit(frame.get("coverage")), "depth coverage is a share")
        # One dark or blank photo may have little depth; the set as a whole may not.
        # The pose model's depth only sets the scale, so it may be sparser than metric depth.
        coverages = sorted(float(f["coverage"]) for f in result.output["frames"])
        _require(
            coverages[len(coverages) // 2] >= MIN_POSE_DEPTH_COVERAGE,
            f"depth covers at least {MIN_POSE_DEPTH_COVERAGE:.0%} of most photos",
        )

    return validate


# The spike reached 25.7 to 26.0 dB on held-out views of phone captures with pose
# refinement and 17 to 18 dB without it. Below this a splat is not shown to anyone.
MIN_SPLAT_PSNR_DB = 20.0


def check_splat() -> Validator:
    def validate(result: ProviderResult) -> None:
        out = result.output
        for key in ("splat", "labels", "cameras"):
            _require(DIGEST.match(str(out.get(key))) is not None, f"{key} is a blob digest")
        gaussians = out.get("gaussians")
        _require(
            isinstance(gaussians, int) and 10_000 <= gaussians <= 8_000_000,
            "gaussian count is plausible",
        )
        psnr = out.get("psnr_heldout")
        _require(
            isinstance(psnr, int | float) and math.isfinite(psnr) and psnr >= MIN_SPLAT_PSNR_DB,
            f"held-out PSNR is at least {MIN_SPLAT_PSNR_DB} dB",
        )

    return validate


# LaMa fills agreed with the fine-tuned splat at 23 to 30 dB in the removal comparison.
MIN_FILL_AGREEMENT_DB = 20.0


def check_removal() -> Validator:
    def validate(result: ProviderResult) -> None:
        out = result.output
        _require(DIGEST.match(str(out.get("splat"))) is not None, "splat is a blob digest")
        gaussians = out.get("gaussians")
        _require(
            isinstance(gaussians, int) and 10_000 <= gaussians <= 8_000_000,
            "gaussian count is plausible",
        )
        removed = out.get("gaussians_removed")
        _require(isinstance(removed, int) and removed > 0, "some Gaussians were removed")
        inpainted = out.get("frames_inpainted")
        _require(isinstance(inpainted, int) and inpainted > 0, "some frames were inpainted")
        agreement = out.get("fill_agreement_psnr")
        _require(
            isinstance(agreement, int | float)
            and math.isfinite(agreement)
            and agreement >= MIN_FILL_AGREEMENT_DB,
            f"the fill agrees across views to at least {MIN_FILL_AGREEMENT_DB} dB",
        )

    return validate


def check_inpaint(payload: Mapping[str, Any]) -> Validator:
    """A filled image per frame asked, in order."""
    asked: Sequence[Mapping[str, Any]] = payload["frames"]

    def validate(result: ProviderResult) -> None:
        for frame in _frames(result, asked):
            _require(DIGEST.match(str(frame.get("filled"))) is not None, "filled is a blob digest")

    return validate
