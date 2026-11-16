"""The phone splat step: decimated, compressed room splats for on-device viewing.

SJ-116 chose on-device SOG with colour only (no view-dependent colour): 500k
Gaussians for capable phones and 250k for budget Android, 3 to 6 MB each with
under 1.5 dB of loss on real rooms. Compression is plain CPU work (PlayCanvas
splat-transform), not a model, so it runs outside the gateway; the step keeps
it durable and checks every variant before it is recorded.
"""

import math
import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any

from sajao_gateway import MICRO_INR_PER_RUPEE
from sajao_workers.gpu import INR_PER_USD
from sajao_workers.steps import NonRetryableStepError, Step, StepContext, StepOutput

# Bump when the budgets, the compression settings or splat-transform change.
VERSION = 1
BUDGETS = (500_000, 250_000)
# Download size a phone can take for one room: the spike measured 3 to 6 MB.
MIN_BYTES, MAX_BYTES = 200_000, 12_000_000
# The compression function's size (gpu/app.py) and Modal's CPU and memory prices.
CPU_CORES, MEMORY_GIB = 16, 32
USD_PER_CORE_SECOND = 0.0473 / 3600
USD_PER_GIB_SECOND = 0.008 / 3600
DIGEST = re.compile(r"^[0-9a-f]{64}$")

# payload {"splat", "budgets"} -> {"source_gaussians", "variants", "cpu_seconds"} or {"error"}
Compress = Callable[[Mapping[str, Any]], Awaitable[Mapping[str, Any]]]


def tag(budget: int) -> str:
    return f"{budget // 1000}k"


def check_variants(variants: Sequence[Mapping[str, Any]], source_gaussians: int) -> None:
    """Raise ValueError unless every budget has a plausible SOG of the right size."""
    by_budget = {v.get("budget"): v for v in variants}
    for budget in BUDGETS:
        variant = by_budget.get(budget)
        if variant is None:
            raise ValueError(f"no {tag(budget)} variant")
        if not DIGEST.match(str(variant.get("sog"))):
            raise ValueError(f"{tag(budget)}: sog is not a blob digest")
        expected = min(budget, source_gaussians)
        if variant.get("gaussians") != expected:
            raise ValueError(f"{tag(budget)}: {variant.get('gaussians')} Gaussians, not {expected}")
        size = variant.get("bytes")
        if not isinstance(size, int) or not MIN_BYTES <= size <= MAX_BYTES:
            raise ValueError(f"{tag(budget)}: {size} bytes is outside the phone range")


def cpu_cost_micro_inr(seconds: float) -> int:
    usd = seconds * (CPU_CORES * USD_PER_CORE_SECOND + MEMORY_GIB * USD_PER_GIB_SECOND)
    return math.ceil(usd * INR_PER_USD * MICRO_INR_PER_RUPEE)


def phone_splat_step(compress: Compress) -> Step:
    async def run(context: StepContext) -> StepOutput:
        reply = await compress({"splat": context.inputs["splat"], "budgets": list(BUDGETS)})
        if "error" in reply:
            raise NonRetryableStepError(str(reply["error"]))
        variants = reply["variants"]
        try:
            check_variants(variants, int(reply["source_gaussians"]))
        except ValueError as error:
            raise NonRetryableStepError(f"phone splat check failed: {error}") from error
        chosen = [v for v in variants if v["budget"] in BUDGETS]
        return StepOutput(
            refs={f"sog_{tag(v['budget'])}": v["sog"] for v in chosen},
            meta={
                "source_gaussians": reply["source_gaussians"],
                "variants": {
                    tag(v["budget"]): {
                        k: v[k] for k in ("gaussians", "bytes", "decimate_method", "seconds")
                    }
                    for v in chosen
                },
            },
            cost_micro_inr=cpu_cost_micro_inr(float(reply.get("cpu_seconds", 0.0))),
        )

    return Step("twin_phone_splat", VERSION, run)
