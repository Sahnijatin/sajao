"""What an adapter hands to the ingest, and what the ingest writes.

A `Listing` is retailer data as found: an adapter (hand curation today, affiliate feeds
later) produces it. A `CatalogEntry` wraps a contract `Product` with what the contract
does not carry yet: where each dimension came from, the fidelity gate result, private
photo locations, the budget band and the permission status.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

GateResult = Literal["pass", "fail", "unverifiable", "not_run"]
Permission = Literal["granted", "not_granted"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ListingDimensions(Strict):
    """Centimetres as the listing states them."""

    width_cm: float = Field(gt=0)
    depth_cm: float = Field(gt=0)
    height_cm: float = Field(gt=0)
    where: str = Field(min_length=1, description="Where on the listing, e.g. spec table")


class Gate(Strict):
    """Per-product fidelity gate: a 3D asset built from one listing photo, scored on the
    listing's other (held-out) photos."""

    result: GateResult
    method: str = Field(min_length=1)
    held_out_photos: int = Field(ge=0)
    scores: list[dict[str, float]] = Field(default_factory=list)


class Freshness(Strict):
    """Last check of the live listing page."""

    checked_at: str = Field(min_length=1, description="RFC 3339 UTC")
    link_ok: bool
    in_stock: bool
    price_inr: float = Field(ge=0)


class Listing(Strict):
    source: str = Field(min_length=1)
    sku: str = Field(min_length=1)
    url: str = Field(pattern=r"^https://\S+$")
    retailer: str = Field(min_length=1)
    title: str = Field(min_length=1)
    brand: str | None = None
    category: str = Field(min_length=1, description="Fine category, e.g. coffee_table")
    room_types: list[Literal["living_room", "bedroom"]] = Field(min_length=1)
    dimensions: ListingDimensions
    color: str | None = None
    material: str | None = None
    style_tags: list[str] = Field(min_length=1)
    images: list[str] = Field(min_length=1, description="Retailer image URLs")
    private_photos: list[str] = Field(
        default_factory=list, description="Copies on the private volume (never shipped)"
    )
    clean_photos: int = Field(ge=0, description="Clean product photos from distinct angles")
    gate: Gate
    freshness: Freshness
    image_use: Permission = "not_granted"
    route: Permission = "not_granted"


class CatalogEntry(Strict):
    stage: Literal["development", "live"]
    product: dict[str, object]
    budget_band: Literal["value", "mid", "premium"]
    room_types: list[str]
    dimension_source: str
    private_photos: list[str]
    clean_photos: int
    gate: Gate
    image_use: Permission
    route: Permission
    flags: list[str]
