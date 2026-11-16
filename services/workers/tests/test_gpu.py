"""GPU model providers and output validators, with fake GPU calls only: no Modal, no keys."""

from collections.abc import Mapping
from typing import Any

import pytest

from sajao_gateway import (
    InMemorySpendLedger,
    InvalidOutputError,
    ModelGateway,
    ModelRequest,
    ProviderError,
    ProviderResult,
    SpendCaps,
)
from sajao_workers.gpu import GpuModelProvider, gpu_cost_micro_inr
from sajao_workers.models import VOCABULARY, detect_chain, segment_chain
from sajao_workers.validate import check_detections, check_masks

ROOMY = SpendCaps(per_user_daily_micro_inr=10**12, global_daily_micro_inr=10**12)
IMAGES = [{"image": "a" * 64, "width": 640, "height": 480}]


def detect_request(images: list[dict[str, Any]] = IMAGES) -> ModelRequest:
    return ModelRequest(
        task="twin_detect",
        modality="vision",
        prompt_id="twin_detect@1",
        payload={"images": images, "vocabulary": list(VOCABULARY)},
    )


def replying(reply: Mapping[str, Any], seen: list[str] | None = None) -> Any:
    async def invoke(model: str, _payload: Mapping[str, Any]) -> Mapping[str, Any]:
        if seen is not None:
            seen.append(model)
        return reply

    return invoke


def detections(*found: dict[str, Any]) -> dict[str, Any]:
    return {"frames": [{"image": "a" * 64, "detections": list(found)}]}


SOFA = {"label": "sofa", "score": 0.91, "box": [10.0, 200.0, 400.0, 470.0]}


def test_gpu_cost_uses_the_pinned_price_and_rounds_up() -> None:
    # L40S 0.000542 USD per second at 88 INR per USD: 47,696 micro-rupees per second.
    assert gpu_cost_micro_inr("L40S", 1.0) == 47_696
    assert gpu_cost_micro_inr("L40S", 0.0) == 0
    assert gpu_cost_micro_inr("L40S", 0.00001) == 1


def test_an_unknown_gpu_type_is_rejected() -> None:
    with pytest.raises(KeyError):
        gpu_cost_micro_inr("H900", 1.0)


async def test_the_provider_charges_measured_gpu_seconds() -> None:
    provider = GpuModelProvider(
        "yoloe", "yoloe@1", "L40S", 120.0, replying({"output": {"x": 1}, "gpu_seconds": 2.0})
    )

    result = await provider.call(detect_request())

    assert result.output == {"x": 1}
    assert result.cost_micro_inr == 2 * 47_696
    assert provider.estimate_cost_micro_inr(detect_request()) == 120 * 47_696


async def test_a_remote_input_error_is_not_retried() -> None:
    provider = GpuModelProvider(
        "yoloe", "yoloe@1", "L40S", 120.0, replying({"error": "image not found"})
    )

    with pytest.raises(ProviderError, match="image not found") as raised:
        await provider.call(detect_request())
    assert not raised.value.retryable


@pytest.mark.parametrize("seconds", [-1.0, float("nan"), "fast", None])
async def test_a_reply_without_valid_gpu_seconds_is_an_error(seconds: object) -> None:
    provider = GpuModelProvider(
        "yoloe", "yoloe@1", "L40S", 120.0, replying({"output": {}, "gpu_seconds": seconds})
    )

    with pytest.raises(ProviderError):
        await provider.call(detect_request())


def test_chains_have_a_primary_and_a_fallback_on_one_capped_gpu_function() -> None:
    async def invoke(_model: str, _payload: Mapping[str, Any]) -> Mapping[str, Any]:
        return {}

    for chain in (detect_chain(invoke), segment_chain(invoke)):
        assert len(chain) >= 2
        assert len({provider.name for provider in chain}) == len(chain)
        assert all("@" in provider.model for provider in chain)  # versions pinned


async def test_the_gateway_falls_back_to_the_second_detector() -> None:
    seen: list[str] = []

    async def invoke(model: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        seen.append(model)
        if model.startswith("yoloe"):
            return {"error": "weights missing"}
        return {"output": detections(SOFA), "gpu_seconds": 1.0}

    request = detect_request()
    gateway = ModelGateway(detect_chain(invoke), ledger=InMemorySpendLedger(ROOMY))
    response = await gateway.call(request, validate=check_detections(request.payload))

    assert response.provider == "grounding-dino"
    assert len(seen) == 2


def test_valid_detections_pass() -> None:
    check_detections(detect_request().payload)(ProviderResult(detections(SOFA)))


@pytest.mark.parametrize(
    "bad",
    [
        {**SOFA, "label": "spaceship"},
        {**SOFA, "score": 1.5},
        {**SOFA, "box": [10.0, 200.0, 700.0, 470.0]},  # past the right edge
        {**SOFA, "box": [400.0, 200.0, 10.0, 470.0]},  # empty
        {**SOFA, "box": [10.0, 200.0, 400.0]},
    ],
)
def test_invalid_detections_are_rejected(bad: dict[str, Any]) -> None:
    with pytest.raises(InvalidOutputError):
        check_detections(detect_request().payload)(ProviderResult(detections(bad)))


def test_detections_for_the_wrong_frames_are_rejected() -> None:
    wrong = {"frames": [{"image": "b" * 64, "detections": []}]}
    with pytest.raises(InvalidOutputError):
        check_detections(detect_request().payload)(ProviderResult(wrong))
    with pytest.raises(InvalidOutputError):
        check_detections(detect_request().payload)(ProviderResult({"frames": []}))


def mask_payload() -> dict[str, Any]:
    return {"frames": [{**IMAGES[0], "boxes": [SOFA["box"]]}]}


def masks(*found: dict[str, Any]) -> dict[str, Any]:
    return {"frames": [{"image": "a" * 64, "masks": list(found)}]}


GOOD_MASK = {"mask": "c" * 64, "area": 50_000, "score": 0.97}


def test_valid_masks_pass() -> None:
    check_masks(mask_payload())(ProviderResult(masks(GOOD_MASK)))


@pytest.mark.parametrize(
    "bad",
    [
        [],  # one mask per box is required
        [GOOD_MASK, GOOD_MASK],
        [{**GOOD_MASK, "area": 0}],
        [{**GOOD_MASK, "area": 640 * 480 + 1}],
        [{**GOOD_MASK, "mask": "not a digest"}],
        [{**GOOD_MASK, "score": -0.1}],
    ],
)
def test_invalid_masks_are_rejected(bad: list[dict[str, Any]]) -> None:
    with pytest.raises(InvalidOutputError):
        check_masks(mask_payload())(ProviderResult(masks(*bad)))
