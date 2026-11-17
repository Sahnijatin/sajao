"""The one ingest path: adapter listings in, validated catalog entries out.

Every entry's product is validated against the `Product` contract. A product enters the
contract only with permission to use its images and a permitted route; until the source
grants both, the entry stays at stage "development", says so in `flags`, and its product
carries `image_use_permitted: false`. Nothing is written as permitted that is not.

Ingest is idempotent: the product id is derived from source and SKU, and re-ingesting a
listing replaces its entry.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterable
from pathlib import Path

from sajao_catalog.bands import FAMILY, band, group
from sajao_catalog.model import CatalogEntry, Listing
from sajao_schemas import SCHEMA_VERSION, Product

NAMESPACE = uuid.UUID("5b1f3c2e-8f8a-4a51-9a4e-2f0d3c7a9e11")
FLAT = {"rug", "wall_art"}  # no fidelity check for flat items yet
# Listing dimensions are unverified retailer data: "estimated" in the contract, with a
# 2 cm band for rounding on the listing.
LISTING_ERROR_BAND_M = 0.02


class Rejected(ValueError):
    """A listing that may not enter the catalog at all."""


def product_id(source: str, sku: str) -> str:
    return str(uuid.uuid5(NAMESPACE, f"{source}:{sku}"))


def _dimension(cm: float) -> dict[str, object]:
    return {
        "value_m": round(cm / 100, 4),
        "source": "estimated",
        "error_band_m": LISTING_ERROR_BAND_M,
    }


def to_entry(item: Listing) -> CatalogEntry:
    if item.category in FLAT:
        raise Rejected(f"{item.sku}: flat items wait for the flat items check (SJ-150)")
    if item.category not in FAMILY:
        raise Rejected(f"{item.sku}: unknown category {item.category}")
    if not item.freshness.link_ok:
        raise Rejected(f"{item.sku}: listing link does not open")
    price = {"currency": "INR", "amount_minor": round(item.freshness.price_inr * 100)}
    permitted = item.image_use == "granted" and item.route == "granted"
    product: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "id": product_id(item.source, item.sku),
        "source": item.source,
        "sku": item.sku,
        "title": item.title,
        "group": group(item.category),
        "category": item.category,
        "dimensions": {
            "width": _dimension(item.dimensions.width_cm),
            "depth": _dimension(item.dimensions.depth_cm),
            "height": _dimension(item.dimensions.height_cm),
        },
        "style_tags": sorted(set(item.style_tags)),
        "price": price,
        "in_stock": item.freshness.in_stock,
        "checked_at": item.freshness.checked_at,
        "images": item.images,
        "image_use_permitted": permitted,
        "routes": [{"kind": "buy", "retailer": item.retailer, "url": item.url, "price": price}],
    }
    for key in ("brand", "color", "material"):
        value = getattr(item, key)
        if value:
            product[key] = value
    # Validate everything the contract checks; the permission field is the one known gap
    # for development products and is reported, not faked.
    Product.model_validate({**product, "image_use_permitted": True})
    flags = []
    if item.image_use != "granted":
        flags.append("image use not granted by the source (engineering rule 9)")
    if item.route != "granted":
        flags.append("no permitted affiliate or rental route yet (engineering rule 9)")
    if not item.freshness.in_stock:
        flags.append("out of stock at last check")
    if item.gate.result != "pass":
        flags.append(f"fidelity gate {item.gate.result}: not placed as an exact product")
    if item.clean_photos < 3:
        flags.append(f"only {item.clean_photos} clean photos")
    return CatalogEntry(
        stage="live" if permitted else "development",
        product=product,
        budget_band=band(item.category, item.freshness.price_inr),
        room_types=list(item.room_types),
        dimension_source=item.dimensions.where,
        private_photos=list(item.private_photos),
        clean_photos=item.clean_photos,
        gate=item.gate,
        image_use=item.image_use,
        route=item.route,
        flags=flags,
    )


def load(path: Path) -> dict[str, CatalogEntry]:
    if not path.exists():
        return {}
    out = {}
    for line in path.read_text().splitlines():
        if line.strip():
            e = CatalogEntry.model_validate_json(line)
            out[str(e.product["id"])] = e
    return out


def ingest(listings: Iterable[Listing], out: Path) -> tuple[list[CatalogEntry], list[str]]:
    """Validate and upsert. Returns (entries written this run, rejection reasons)."""
    entries = load(out)
    written, rejected = [], []
    for item in listings:
        try:
            e = to_entry(item)
        except (Rejected, ValueError) as err:
            rejected.append(str(err).splitlines()[0])
            continue
        entries[str(e.product["id"])] = e
        written.append(e)
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        json.dumps(e.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
        for _, e in sorted(entries.items())
    ]
    out.write_text("\n".join(lines) + "\n")
    return written, rejected
