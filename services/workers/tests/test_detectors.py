"""The detector vocabulary (general plus Indian home names) and the swappable chain."""

from collections.abc import Mapping
from typing import Any

import pytest

from sajao_workers.models import (
    DETECTORS,
    GENERAL_VOCABULARY,
    GROUNDING_DINO,
    INDIAN_VOCABULARY,
    OWLV2,
    PROMPTS,
    VOCABULARY,
    YOLOE,
    detect_chain,
    detector_order,
    prompts_for,
)


async def invoke(_model: str, _payload: Mapping[str, Any]) -> Mapping[str, Any]:
    return {}


def test_the_vocabulary_is_the_general_list_then_the_indian_names() -> None:
    assert VOCABULARY == GENERAL_VOCABULARY + INDIAN_VOCABULARY
    assert len(set(VOCABULARY)) == len(VOCABULARY)
    assert all(name == name.lower().strip() for name in VOCABULARY)
    for name in ("almirah", "diwan", "puja unit", "geyser", "air cooler", "water purifier"):
        assert name in INDIAN_VOCABULARY
    assert "shoe rack" in INDIAN_VOCABULARY


def test_every_class_has_a_prompt_and_overrides_only_name_known_classes() -> None:
    prompts = prompts_for(VOCABULARY)
    assert len(prompts) == len(VOCABULARY)
    assert set(PROMPTS) <= set(VOCABULARY)
    assert prompts[VOCABULARY.index("sofa")] == "sofa"  # no override: the name itself
    assert prompts[VOCABULARY.index("puja unit")] == PROMPTS["puja unit"]


def test_the_default_chain_is_yoloe_then_grounding_dino_then_owlv2() -> None:
    assert [p.model for p in detect_chain(invoke)] == [YOLOE, GROUNDING_DINO, OWLV2]


def test_a_chain_without_yoloe_can_be_chosen_in_one_line() -> None:
    chain = detect_chain(invoke, order=("owlv2", "grounding-dino"))
    assert [p.model for p in chain] == [OWLV2, GROUNDING_DINO]


def test_an_unknown_detector_is_refused() -> None:
    with pytest.raises(ValueError, match="unknown detector"):
        detect_chain(invoke, order=("yolo-world",))


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        ({}, DETECTORS),
        ({"SAJAO_DETECTORS": "owlv2,grounding-dino"}, ("owlv2", "grounding-dino")),
        ({"SAJAO_DETECTORS": " owlv2 , yoloe "}, ("owlv2", "yoloe")),
    ],
)
def test_the_detector_order_comes_from_the_environment(
    env: dict[str, str], expected: tuple[str, ...]
) -> None:
    assert detector_order(env) == expected
