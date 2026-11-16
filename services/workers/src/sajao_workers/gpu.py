"""Self-hosted GPU models as gateway providers.

Every GPU model runs in one Modal function capped at three containers, so the
whole pipeline never holds more than three GPUs. A provider is one pinned model
on that function. It charges what the call really used (GPU seconds times the
pinned price) and reserves the worst case (its time limit) against spend caps.
"""

import math
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from sajao_gateway import MICRO_INR_PER_RUPEE, ModelRequest, ProviderError, ProviderResult
from sajao_gateway.types import Modality

# Modal list prices per GPU second. Update with the price source when they change.
GPU_USD_PER_SECOND = {"L40S": 0.000542, "L4": 0.000222, "T4": 0.000164}
# Pinned conversion for cost accounting; spend reports use the same number.
INR_PER_USD = 88
# The Modal GPU function's max_containers. The provider limit matches it.
MAX_GPUS = 3

# (pinned model, request payload) -> {"output": ..., "gpu_seconds": ...} or {"error": ...}
Invoke = Callable[[str, Mapping[str, Any]], Awaitable[Mapping[str, Any]]]


def gpu_cost_micro_inr(gpu: str, seconds: float) -> int:
    return math.ceil(seconds * GPU_USD_PER_SECOND[gpu] * INR_PER_USD * MICRO_INR_PER_RUPEE)


@dataclass
class GpuModelProvider:
    name: str
    model: str  # Pinned: name@version or name@revision.
    gpu: str
    max_seconds: float  # The remote time limit; the most one call can cost.
    invoke: Invoke
    modalities: frozenset[Modality] = field(default=frozenset({"vision"}))
    max_concurrency: int = MAX_GPUS

    def estimate_cost_micro_inr(self, request: ModelRequest) -> int:
        return gpu_cost_micro_inr(self.gpu, self.max_seconds)

    async def call(self, request: ModelRequest) -> ProviderResult:
        reply = await self.invoke(self.model, request.payload)
        if "error" in reply:
            # The GPU function reports input it can never process; retrying cannot help.
            raise ProviderError(str(reply["error"]), retryable=False)
        seconds = reply.get("gpu_seconds")
        if not isinstance(seconds, int | float) or not math.isfinite(seconds) or seconds < 0:
            raise ProviderError("reply has no valid gpu_seconds")
        return ProviderResult(reply["output"], cost_micro_inr=gpu_cost_micro_inr(self.gpu, seconds))
