from __future__ import annotations

from sajao_catalog.ingest import to_entry
from sajao_catalog.model import Listing
from sajao_catalog.visibility import ENV, flagged_allowed, may_show

RAW = {
    "source": "wooden_street",
    "sku": "ws_example-chair",
    "url": "https://www.woodenstreet.com/example-chair",
    "retailer": "Wooden Street",
    "title": "Example Chair",
    "category": "armchair",
    "room_types": ["living_room"],
    "dimensions": {"width_cm": 70, "depth_cm": 75, "height_cm": 80, "where": "spec table"},
    "style_tags": ["japandi"],
    "images": ["https://images.example.com/c.jpg"],
    "clean_photos": 3,
    "gate": {"result": "pass", "method": "test", "held_out_photos": 2},
    "freshness": {
        "checked_at": "2026-01-01T00:00:00Z",
        "link_ok": True,
        "in_stock": True,
        "price_inr": 12999,
    },
}


def test_store_release_hides_flagged_products() -> None:
    dev = to_entry(Listing.model_validate(RAW))
    assert dev.product["image_use_permitted"] is False
    assert not may_show(dev, allow_flagged=False)
    assert may_show(dev, allow_flagged=True)


def test_permitted_products_show_everywhere() -> None:
    live = to_entry(Listing.model_validate({**RAW, "image_use": "granted", "route": "granted"}))
    assert may_show(live, allow_flagged=False)


def test_setting_is_off_unless_turned_on() -> None:
    assert not flagged_allowed({})
    assert not flagged_allowed({ENV: "0"})
    assert flagged_allowed({ENV: "1"})
