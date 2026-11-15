"""Fake providers for tests. No network, no keys."""

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass, field

from sajao_gateway.types import Modality, ModelRequest, ProviderResult

Step = ProviderResult | Exception


@dataclass
class FakeProvider:
    """Plays back a script of results and errors, then repeats the last step."""

    name: str
    script: Sequence[Step]
    model: str = "fake-1"
    modalities: frozenset[Modality] = frozenset({"text", "vision", "image"})
    max_concurrency: int = 4
    estimated_cost_micro_inr: int = 1_000
    # When set, each call waits here, so tests can hold calls in flight.
    hold: asyncio.Event | None = None
    calls: list[ModelRequest] = field(default_factory=list)
    in_flight: int = 0
    peak_in_flight: int = 0

    def estimate_cost_micro_inr(self, request: ModelRequest) -> int:
        return self.estimated_cost_micro_inr

    async def call(self, request: ModelRequest) -> ProviderResult:
        step = self.script[min(len(self.calls), len(self.script) - 1)]
        self.calls.append(request)
        self.in_flight += 1
        self.peak_in_flight = max(self.peak_in_flight, self.in_flight)
        try:
            if self.hold is not None:
                await self.hold.wait()
            if isinstance(step, Exception):
                raise step
            return step
        finally:
            self.in_flight -= 1
