"""Round-trip tests: fixture JSON -> Pydantic -> JSON must be lossless and schema-valid."""

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from sajao_schemas import OBJECTS, Dimension, to_json_dict

PACKAGE = Path(__file__).resolve().parents[2]
FIXTURES = PACKAGE / "fixtures" / "v1"
BUNDLE: dict[str, Any] = json.loads((PACKAGE / "generated" / "v1.schema.json").read_text())


def object_name(path: Path) -> str:
    """room-profile.dimension-without-source.json -> RoomProfile"""
    return "".join(part.capitalize() for part in path.name.split(".")[0].split("-"))


def schema_validator(name: str) -> Draft202012Validator:
    schema = {"$ref": f"#/$defs/{name}", "$defs": BUNDLE["$defs"]}
    return Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)


VALID = sorted((FIXTURES / "valid").glob("*.json"))
INVALID = sorted((FIXTURES / "invalid").glob("*.json"))


def test_models_cover_exactly_the_objects_the_schemas_define() -> None:
    assert sorted(OBJECTS) == sorted(BUNDLE["x-top-level"])
    assert sorted(object_name(path) for path in VALID) == sorted(OBJECTS)


@pytest.mark.parametrize("path", VALID, ids=lambda p: p.name)
def test_valid_fixture_round_trips(path: Path) -> None:
    name = object_name(path)
    data = json.loads(path.read_text())
    assert list(schema_validator(name).iter_errors(data)) == []

    dumped = to_json_dict(OBJECTS[name].model_validate(data))

    assert dumped == data
    assert list(schema_validator(name).iter_errors(dumped)) == []
    # The serialised text parses back to the same object.
    again = OBJECTS[name].model_validate_json(json.dumps(dumped))
    assert to_json_dict(again) == data


@pytest.mark.parametrize("path", INVALID, ids=lambda p: p.name)
def test_invalid_fixture_is_rejected_by_schema_and_model(path: Path) -> None:
    name = object_name(path)
    data = json.loads(path.read_text())
    assert list(schema_validator(name).iter_errors(data)) != []
    with pytest.raises(ValidationError):
        OBJECTS[name].model_validate(data)


def test_every_dimension_needs_value_source_and_error_band() -> None:
    full = {"value_m": 3.4, "source": "estimated", "error_band_m": 0.12}
    assert to_json_dict(Dimension.model_validate(full)) == full
    for missing in full:
        partial = {key: value for key, value in full.items() if key != missing}
        with pytest.raises(ValidationError):
            Dimension.model_validate(partial)
