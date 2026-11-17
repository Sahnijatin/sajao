import asyncio
from pathlib import Path
from typing import Any

import pytest

from sajao_dataset import evalset as ev
from sajao_gateway import InvalidOutputError, ModelRequest, ProviderResult, SpendCapExceededError


def result(output: dict[str, Any]) -> ProviderResult:
    return ProviderResult(output=output, cost_micro_inr=0)


def test_listed_names_map_to_classes() -> None:
    assert ev.class_of("Ceiling Fans") == "ceiling_fan"
    assert ev.class_of("RO Water Purifier") == "water_purifier"
    assert ev.class_of("mandir") == "pooja_unit"
    assert ev.class_of("Split AC") == "ac_unit"
    assert ev.class_of("pedestal fan") is None
    assert ev.class_of("showpiece") is None


def test_every_target_is_in_the_taxonomy_and_aliases_are_unique() -> None:
    assert set(ev.TARGETS) <= set(ev.TAXONOMY)
    aliases = [a for _, names in ev.TAXONOMY.values() for a in names]
    assert len(aliases) == len(set(aliases))
    assert all(ev.normalise(a) == a for a in aliases)


def frame(
    clip: str, t: float, sharp: float, room: str = "kitchen", width: int = 1280
) -> dict[str, Any]:
    return {
        "video_id": clip.split("/")[0],
        "clip_path": clip,
        "path": f"{clip}-{t}.jpg",
        "t_s": t,
        "sharpness": sharp,
        "room_type": room,
        "width": width,
    }


def test_pool_takes_the_sharpest_frames_apart_in_time() -> None:
    frames = [
        frame("v/a", 0.0, 50),
        frame("v/a", 1.0, 90),
        frame("v/a", 2.0, 80),  # within 3 s of the sharpest
        frame("v/a", 6.0, 70),
        frame("v/b", 0.0, 99, room="corridor"),  # no target room
        frame("v/c", 0.0, 99, width=360),  # portrait or small
    ]
    pool = ev.pool_frames(frames)
    assert [f["t_s"] for f in pool] == [1.0, 6.0]


def test_label_validation() -> None:
    ev.check_labels(result({"objects": [{"class": "geyser", "box_2d": [10, 10, 200, 200]}]}))
    with pytest.raises(InvalidOutputError):
        ev.check_labels(result({"objects": [{"class": "lamp", "box_2d": [10, 10, 200, 200]}]}))
    for bad in ([10, 10, 5, 200], [0, 0, 1001, 10], [1, 2, 3], [10, 10, 12, 12]):
        with pytest.raises(InvalidOutputError):
            ev.check_labels(result({"objects": [{"class": "geyser", "box_2d": bad}]}))


def test_review_needs_one_verdict_per_label() -> None:
    check = ev.check_review_for(2)
    ok: dict[str, Any] = {
        "reviews": [
            {"id": 1, "verdict": "agree", "correct_class": "sofa"},
            {"id": 2, "verdict": "wrong_class", "correct_class": "diwan"},
        ],
        "missed": [{"class": "ceiling_fan", "box_2d": [0, 400, 80, 600]}],
    }
    check(result(ok))
    with pytest.raises(InvalidOutputError):
        check(result({**ok, "reviews": ok["reviews"][:1]}))
    with pytest.raises(InvalidOutputError):
        check(result({**ok, "missed": [{"class": "ceiling_fan", "box_2d": [0, 0, 0, 0]}]}))


def tagged(n: int, present: list[str], video: str, room: str = "kitchen") -> list[dict[str, Any]]:
    return [
        {
            "path": f"{video}/{i}.jpg",
            "clip_path": f"{video}/clip{i}",
            "video_id": video,
            "room_type": room,
            "present": present,
        }
        for i in range(n)
    ]


def test_selection_fills_rare_targets_first_and_spreads_videos() -> None:
    pool = (
        tagged(3, ["diwan"], "v1", "living_room")
        + tagged(30, ["gas_stove", "modular_kitchen"], "v2")
        + tagged(30, ["gas_stove"], "v3")
        + tagged(30, ["sofa"], "v4", "living_room")
    )
    pick = ev.select_stratified(pool, total=20, quota=5, max_per_video=6)
    assert len(pick.frames) == 20
    assert pick.per_class["diwan"] == 3
    assert pick.short["diwan"] == 2
    assert pick.per_class["gas_stove"] >= 5
    assert max(sum(f["video_id"] == v for f in pick.frames) for v in ("v2", "v3", "v4")) <= 6
    assert len({f["clip_path"] for f in pick.frames}) == 20
    again = ev.select_stratified(pool, total=20, quota=5, max_per_video=6)
    assert [f["path"] for f in again.frames] == [f["path"] for f in pick.frames]


LABELS = [
    {"class": "gas_stove", "box_2d": [500, 100, 600, 300]},
    {"class": "sofa", "box_2d": [500, 500, 900, 900]},
]
REVIEW = {
    "reviews": [
        {"id": 1, "verdict": "agree", "correct_class": "gas_stove"},
        {"id": 2, "verdict": "wrong_class", "correct_class": "diwan"},
    ],
    "missed": [{"class": "geyser", "box_2d": [0, 0, 100, 100]}],
}


def test_disagreements_and_final_objects() -> None:
    items = ev.disagreements(LABELS, REVIEW)
    assert [(i["item"], i["verdict"], i["suggested_class"]) for i in items] == [
        ("label-2", "wrong_class", "diwan"),
        ("missed-1", "missed", "geyser"),
    ]
    objects, unresolved = ev.final_objects(LABELS, REVIEW, None)
    assert [o["class"] for o in objects] == ["gas_stove"] and unresolved == 2
    decisions = {
        "label-2": {"decision": "relabel", "class": "diwan"},
        "missed-1": {"decision": "drop"},
    }
    objects, unresolved = ev.final_objects(LABELS, REVIEW, decisions)
    assert [o["class"] for o in objects] == ["gas_stove", "diwan"] and unresolved == 0


def test_listing_score_per_class() -> None:
    found, other = ev.listed_classes(
        [
            {"name": "Gas Stove", "prompts": []},
            {"name": "almirah", "prompts": ["wardrobe"]},
            {"name": "matka", "prompts": ["clay pot"]},
        ]
    )
    assert found == {"gas_stove", "almirah"} and other == ["matka"]
    truth = {"a": {"gas_stove", "geyser"}, "b": {"geyser"}, "c": set()}
    listed = {"a": {"gas_stove"}, "b": {"geyser"}, "c": {"geyser"}}
    s = ev.score_listing(truth, listed)
    assert s["geyser"]["recall"] == 0.5 and s["geyser"]["precision"] == 0.5
    assert s["gas_stove"]["recall"] == 1.0
    assert s["all"]["listed_right"] == 2 and s["all"]["missed"] == 1


def test_monthly_ledger_caps_across_runs(tmp_path: Path) -> None:
    path = tmp_path / "spend.jsonl"

    async def run() -> None:
        ledger = ev.MonthlySpendLedger(path, 1000, month="2026-11")
        held = await ledger.reserve(None, 600)
        with pytest.raises(SpendCapExceededError):
            await ledger.reserve(None, 600)
        ledger.record(500, "t")
        await ledger.settle(held, 500)
        again = ev.MonthlySpendLedger(path, 1000, month="2026-11")
        assert again.spent() == 500
        with pytest.raises(SpendCapExceededError):
            await again.reserve(None, 600)
        assert ev.MonthlySpendLedger(path, 1000, month="2026-12").spent() == 0

    asyncio.run(run())


class Refuses:
    name = "fake"
    model = "fake-1"
    modalities = frozenset({"vision"})
    timeout_seconds = 10.0

    def estimate_cost_micro_inr(self, request: ModelRequest) -> int:
        return 77

    async def call(self, request: ModelRequest) -> ProviderResult:
        raise InvalidOutputError("the model declined")


def test_billed_provider_records_failed_calls_at_their_estimate(tmp_path: Path) -> None:
    ledger = ev.MonthlySpendLedger(tmp_path / "spend.jsonl", 1000)
    provider = ev.BilledProvider(Refuses(), ledger)
    request = ModelRequest("t", "vision", "p@1", {})
    with pytest.raises(InvalidOutputError):
        asyncio.run(provider.call(request))
    assert ledger.spent() == 77
