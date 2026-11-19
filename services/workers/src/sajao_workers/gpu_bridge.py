"""Calls to the GPU worker from a pipeline whose blobs live in another store.

The GPU functions read and write blobs, by digest, in the shared store on the
worker's volume. The room pipeline keeps each user's blobs in their own folder,
which account erasure deletes. `bridged` wraps a gateway invoke so a call copies
the blobs its payload names into the shared store, runs, copies the blobs its
reply names back into the user's store, and deletes every copy it made from the
shared store, so nothing of the user's stays there.
"""

import re
from collections.abc import Awaitable, Callable, Iterator, Mapping
from typing import Any

from sajao_workers.gpu import Invoke
from sajao_workers.steps import ArtifactStore, LocalArtifactStore

DIGEST = re.compile(r"^[0-9a-f]{64}$")
Sync = Callable[[], Awaitable[None]]


async def _nothing() -> None:
    return None


def digests(value: Any) -> Iterator[str]:
    """Every blob digest in a JSON-like value."""
    if isinstance(value, str):
        if DIGEST.match(value):
            yield value
    elif isinstance(value, Mapping):
        for item in value.values():
            yield from digests(item)
    elif isinstance(value, list | tuple):
        for item in value:
            yield from digests(item)


def bridged(
    invoke: Invoke,
    local: ArtifactStore,
    shared: LocalArtifactStore,
    publish: Sync = _nothing,
    refresh: Sync = _nothing,
) -> Invoke:
    """`invoke` with its blobs copied over and back. `publish` makes the shared store's
    writes visible to the GPU (a volume commit); `refresh` makes the GPU's writes
    visible here (a volume reload)."""

    async def call(model: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        sent = {d for d in digests(payload) if local.has_blob(d)}
        copied = [d for d in sorted(sent) if not shared.has_blob(d)]
        for d in copied:
            shared.put_blob(local.read_blob(d))
        made: set[str] = set()
        try:
            if copied:
                await publish()
            reply = await invoke(model, payload)
            await refresh()
            made = {d for d in digests(reply) if d not in sent and shared.has_blob(d)}
            for d in sorted(made):
                local.put_blob(shared.read_blob(d))
            return reply
        finally:
            for d in [*copied, *sorted(made)]:
                shared.delete_blob(d)
            if copied or made:
                await publish()

    return call
