"""The Sajao contract as Pydantic models, generated from the JSON schemas.

Validate at every boundary: parse incoming data with these models and
serialise with ``to_json_dict`` so the output matches the schemas exactly.
"""

from typing import Any

from pydantic import BaseModel

from sajao_schemas.generated.v1 import (
    Brief,
    Capture,
    Design,
    Dimension,
    Event,
    Money,
    Plan,
    Product,
    Render,
    ShoppingList,
    SpaceProfile,
    SpaceTwin,
    TasteProfile,
)

SCHEMA_VERSION = "1.0"

OBJECTS: dict[str, type[BaseModel]] = {
    model.__name__: model
    for model in (
        Capture,
        SpaceProfile,
        SpaceTwin,
        TasteProfile,
        Brief,
        Product,
        Design,
        Render,
        Plan,
        ShoppingList,
        Event,
    )
}


def to_json_dict(obj: BaseModel) -> dict[str, Any]:
    """Serialise a contract object to JSON-ready data that validates against its schema."""
    return obj.model_dump(mode="json", exclude_unset=True)


__all__ = [
    "OBJECTS",
    "SCHEMA_VERSION",
    "Brief",
    "Capture",
    "Design",
    "Dimension",
    "Event",
    "Money",
    "Plan",
    "Product",
    "Render",
    "ShoppingList",
    "SpaceProfile",
    "TasteProfile",
    "to_json_dict",
]
