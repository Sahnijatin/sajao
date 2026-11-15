"""Response cache keyed by content hash."""

from typing import Protocol

from sajao_gateway.types import ModelResponse


class ResponseCache(Protocol):
    async def get(self, key: str) -> ModelResponse | None: ...

    async def set(self, key: str, response: ModelResponse) -> None: ...


class InMemoryResponseCache:
    """For tests and single-process jobs. Services use a shared cache with the same contract."""

    def __init__(self) -> None:
        self._entries: dict[str, ModelResponse] = {}

    async def get(self, key: str) -> ModelResponse | None:
        return self._entries.get(key)

    async def set(self, key: str, response: ModelResponse) -> None:
        self._entries[key] = response
