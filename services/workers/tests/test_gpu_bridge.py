"""GPU calls from a pipeline whose blobs live in another store."""

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from sajao_workers.gpu_bridge import bridged, digests
from sajao_workers.steps import LocalArtifactStore


def stores(tmp_path: Path) -> tuple[LocalArtifactStore, LocalArtifactStore]:
    return LocalArtifactStore(tmp_path / "user"), LocalArtifactStore(tmp_path / "shared")


def test_digests_are_found_anywhere_in_the_payload() -> None:
    a, b = "a" * 64, "b" * 64
    found = set(digests({"frames": [{"image": a, "masks": [{"mask": b}]}, "x", 3]}))
    assert found == {a, b}
    assert not set(digests({"label": "sofa", "short": "abc"}))


async def test_inputs_go_over_outputs_come_back_and_no_copy_stays(tmp_path: Path) -> None:
    user, shared = stores(tmp_path)
    image = user.put_blob(b"photo")
    events: list[str] = []

    async def gpu(model: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        events.append("call")
        assert shared.read_blob(payload["frames"][0]["image"]) == b"photo"
        return {
            "frames": [{"image": payload["frames"][0]["image"], "depth": shared.put_blob(b"d")}]
        }

    async def publish() -> None:
        events.append("publish")

    async def refresh() -> None:
        events.append("refresh")

    call = bridged(gpu, user, shared, publish, refresh)
    reply = await call("moge", {"frames": [{"image": image}]})

    depth = reply["frames"][0]["depth"]
    assert user.read_blob(depth) == b"d"
    assert not shared.has_blob(image) and not shared.has_blob(depth)
    assert events == ["publish", "call", "refresh", "publish"]


async def test_a_failed_call_leaves_no_copy(tmp_path: Path) -> None:
    user, shared = stores(tmp_path)
    image = user.put_blob(b"photo")

    async def gpu(model: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        raise RuntimeError("no GPU")

    with pytest.raises(RuntimeError):
        await bridged(gpu, user, shared)("moge", {"image": image})
    assert not shared.has_blob(image)


async def test_blobs_already_shared_are_left_alone(tmp_path: Path) -> None:
    user, shared = stores(tmp_path)
    image = user.put_blob(b"photo")
    shared.put_blob(b"photo")  # another room's copy, mid-call

    async def gpu(model: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        return {"ok": True}

    await bridged(gpu, user, shared)("moge", {"image": image})
    assert shared.has_blob(image)
