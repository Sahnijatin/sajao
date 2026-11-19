"""A design request through the pipeline: rows moved, designs stored, ids copied."""

import json
from pathlib import Path
from typing import Any

from sajao_engine.intents import default_brief
from sajao_engine.testing import OpeningSpec, living_kit, rect, twin_from_polygon
from sajao_schemas import to_json_dict
from sajao_workers.design_pipeline import catalog_products, run_design_request

WHEN = "2026-11-19T00:00:00Z"


class Board:
    def __init__(self) -> None:
        self.moves: list[tuple[str, str, str | None]] = []
        self.designs: list[dict[str, Any]] | None = None

    async def set_stage(self, room_id, stage, status, detail=None, request_id=None) -> None:  # type: ignore[no-untyped-def]
        assert request_id == "req-1"
        self.moves.append((stage, status, detail))

    async def set_designs(self, request_id: str, designs: list[dict[str, Any]]) -> None:
        self.designs = designs


def room() -> Any:
    return twin_from_polygon(
        "pipe", rect(5.0, 4.0), openings=[OpeningSpec("d1", "door", 3, 0.4, 0.9, "start", "inward")]
    )


async def test_three_designs_are_stored_with_the_apps_profile_ids() -> None:
    twin = room()
    brief = to_json_dict(default_brief(twin, WHEN, budget_rupees=300_000))
    brief["space_profile_id"] = "11111111-2222-4333-8444-555555555555"  # made by the app
    board = Board()
    out = await run_design_request(
        board, "room-1", "req-1", brief, to_json_dict(twin), list(living_kit().values()), WHEN
    )
    assert out.outcome == "done"
    assert board.moves == [
        ("spec", "running", None),
        ("spec", "done", None),
        ("placement", "running", None),
        ("placement", "done", None),
    ]
    assert board.designs is not None and len(board.designs) >= 1
    for design in board.designs:
        assert design["space_profile_id"] == brief["space_profile_id"]
        assert design["brief_id"] == brief["id"]
        assert design["slot"] in ("best_match", "best_value", "bold")


async def test_a_room_not_ready_or_not_supported_fails_with_a_reason() -> None:
    twin = room()
    brief = to_json_dict(default_brief(twin, WHEN))
    board = Board()
    out = await run_design_request(board, "room-1", "req-1", brief, None, [], WHEN)
    assert out.outcome == "failed" and board.moves[-1] == ("spec", "failed", "room_not_ready")
    other = to_json_dict(twin) | {"space_type": "balcony"}
    board = Board()
    await run_design_request(board, "room-1", "req-1", brief, other, [], WHEN)
    assert board.moves[-1] == ("spec", "failed", "space_not_supported")


def test_development_products_only_where_the_build_allows(tmp_path: Path) -> None:
    rows = [
        json.loads(line)
        for line in Path(Path(__file__).parents[2] / "catalog/data/development/catalog.jsonl")
        .read_text()
        .splitlines()
    ]
    path = tmp_path / "c.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows))
    shown = catalog_products(path, allow_flagged=True)
    assert len(shown) == sum(r["gate"]["result"] == "pass" for r in rows)
    assert catalog_products(path, allow_flagged=False) == []
