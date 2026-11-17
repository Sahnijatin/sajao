from __future__ import annotations

import json
from pathlib import Path

import pytest

from sajao_catalog.bands import band
from sajao_catalog.cli import main
from sajao_catalog.coverage import table
from sajao_catalog.ingest import ingest, load, product_id, to_entry
from sajao_catalog.model import Listing
from sajao_schemas import Product

RAW = {
    "source": "wooden_street",
    "sku": "ws_example-sofa",
    "url": "https://www.woodenstreet.com/example-sofa",
    "retailer": "Wooden Street",
    "title": "Example 3 Seater Sofa",
    "category": "sofa",
    "room_types": ["living_room"],
    "dimensions": {"width_cm": 210, "depth_cm": 88, "height_cm": 84, "where": "spec table"},
    "style_tags": ["modern_indian", "warm_luxe"],
    "images": ["https://images.example.com/a.jpg", "https://images.example.com/b.jpg"],
    "private_photos": ["modal://sajao-catalog/photos/ws_example-sofa/0.jpg"],
    "clean_photos": 4,
    "gate": {"result": "pass", "method": "triposg+dinov3", "held_out_photos": 3},
    "freshness": {
        "checked_at": "2026-01-01T00:00:00Z",
        "link_ok": True,
        "in_stock": True,
        "price_inr": 54999,
    },
}


def listing(**over: object) -> Listing:
    return Listing.model_validate({**RAW, **over})


def test_entry_validates_against_the_product_contract() -> None:
    e = to_entry(listing())
    p = e.product
    assert p["id"] == product_id("wooden_street", "ws_example-sofa")
    assert p["price"] == {"currency": "INR", "amount_minor": 5_499_900}
    dims = p["dimensions"]
    assert isinstance(dims, dict)
    assert dims["width"] == {"value_m": 2.1, "source": "estimated", "error_band_m": 0.02}
    Product.model_validate({**p, "image_use_permitted": True})


def test_missing_permissions_are_reported_never_faked() -> None:
    e = to_entry(listing())
    assert e.stage == "development"
    assert e.product["image_use_permitted"] is False
    assert any("image use not granted" in f for f in e.flags)
    assert any("affiliate or rental route" in f for f in e.flags)
    live = to_entry(listing(image_use="granted", route="granted"))
    assert live.stage == "live"
    assert live.product["image_use_permitted"] is True
    Product.model_validate(live.product)


def test_flat_items_and_dead_links_are_rejected(tmp_path: Path) -> None:
    rug = listing(sku="rug-1", category="rug")
    dead = listing(sku="dead-1", freshness={**RAW["freshness"], "link_ok": False})  # type: ignore[dict-item]
    written, rejected = ingest([rug, dead, listing()], tmp_path / "c.jsonl")
    assert len(written) == 1
    assert any("flat items" in r for r in rejected)
    assert any("does not open" in r for r in rejected)


def test_gate_and_stock_are_flagged() -> None:
    e = to_entry(
        listing(
            gate={"result": "unverifiable", "method": "triposg+dinov3", "held_out_photos": 0},
            freshness={**RAW["freshness"], "in_stock": False},  # type: ignore[dict-item]
        )
    )
    assert any("fidelity gate unverifiable" in f for f in e.flags)
    assert any("out of stock" in f for f in e.flags)


def test_ingest_is_idempotent(tmp_path: Path) -> None:
    out = tmp_path / "c.jsonl"
    ingest([listing()], out)
    first = out.read_text()
    ingest([listing()], out)
    assert out.read_text() == first
    ingest([listing(freshness={**RAW["freshness"], "price_inr": 49999})], out)  # type: ignore[dict-item]
    entries = load(out)
    assert len(entries) == 1
    only = next(iter(entries.values()))
    assert only.product["price"] == {"currency": "INR", "amount_minor": 4_999_900}


@pytest.mark.parametrize(
    ("category", "price", "expected"),
    [
        ("sofa", 30000, "value"),
        ("sofa", 50000, "mid"),
        ("sofa", 90000, "premium"),
        ("floor_lamp", 1500, "value"),
        ("wardrobe", 40000, "premium"),
    ],
)
def test_bands(category: str, price: float, expected: str) -> None:
    assert band(category, price) == expected


def test_cli_and_coverage(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    src = tmp_path / "in.json"
    src.write_text(json.dumps([RAW]))
    out = tmp_path / "c.jsonl"
    assert main(["ingest", "--adapter", "curated", "--input", str(src), "--out", str(out)]) == 0
    assert main(["coverage", "--catalog", str(out)]) == 0
    printed = capsys.readouterr().out
    assert "| sofa | 1 |" in printed
    t = table(list(load(out).values()))
    assert "0/1/0" in t  # mid band in both tagged styles
