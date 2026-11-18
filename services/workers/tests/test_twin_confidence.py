"""The confidence level of a room's measurements: taped, AR-measured or estimated."""

import pytest

from sajao_workers.twin.confidence import confidence_level, fit_claims


def test_lidar_and_ar_planes_measure_the_room() -> None:
    assert confidence_level("lidar") == {"level": "ar_measured", "basis": "lidar", "tape_values": 0}
    assert confidence_level("ar_planes")["level"] == "ar_measured"


def test_a_depth_model_only_estimates() -> None:
    assert confidence_level("depth_model") == {
        "level": "estimated",
        "basis": "depth_model",
        "tape_values": 0,
    }


def test_one_tape_value_that_agrees_makes_an_ar_room_taped() -> None:
    out = confidence_level("ar_planes", tape_values=1, tape_agrees=True)
    assert out == {"level": "taped", "basis": "tape", "tape_values": 1}


def test_a_tape_value_that_disagrees_with_the_ar_walls_drops_the_room_to_estimated() -> None:
    assert confidence_level("lidar", tape_values=1, tape_agrees=False)["level"] == "estimated"


def test_one_tape_value_fixes_an_estimated_rooms_scale_not_its_shape() -> None:
    # Photos path: one tape value leaves the other walls off by a median 17%.
    assert confidence_level("depth_model", tape_values=1, tape_agrees=True)["level"] == "estimated"


def test_an_estimated_room_is_taped_once_every_wall_it_needs_is_taped() -> None:
    out = confidence_level("depth_model", tape_values=2, tape_agrees=True, walls_needing_tape=2)
    assert out["level"] == "taped"


def test_fit_claims_only_for_taped_and_ar_measured_rooms() -> None:
    assert fit_claims({"level": "taped", "basis": "tape"}) is True
    assert fit_claims({"level": "ar_measured", "basis": "lidar"}) is True
    assert fit_claims({"level": "estimated", "basis": "depth_model"}) is False
    assert fit_claims(None) is False  # a twin from before confidence levels


def test_an_unknown_basis_is_refused() -> None:
    with pytest.raises(ValueError):
        confidence_level("guess")  # type: ignore[arg-type]
