"""Cost arithmetic for the bake-off: Modal rates, asset tiers and cost per design.

Rates are Modal's list prices (per second) at the time of the run; INR at the Spends
ledger rate. Nothing here calls a provider.
"""

from __future__ import annotations

from dataclasses import dataclass

USD_TO_INR = 95.0
GPU_USD_PER_S = {
    "H100": 0.001097,
    "L40S": 0.000542,
    "A10": 0.000306,
    "L4": 0.000222,
    "T4": 0.000164,
}
CPU_CORE_USD_PER_S = 0.0000131
MEM_GIB_USD_PER_S = 0.00000222


def gpu_usd(gpu: str, seconds: float) -> float:
    return GPU_USD_PER_S[gpu] * seconds


def cpu_usd(seconds: float, cores: float = 4.0, mem_gib: float = 8.0) -> float:
    return seconds * (cores * CPU_CORE_USD_PER_S + mem_gib * MEM_GIB_USD_PER_S)


@dataclass(frozen=True)
class DesignCost:
    """Per-design steps in USD. `clear` is one fill-B pass; `light` is one lighting pass
    on one hero view; `compose` is the composite (splat render plus Cycles)."""

    llm: float
    compose: float
    clear: float
    light: float
    hero_views: int = 2

    def plain(self) -> float:
        """Every design clears its own scene and lights every hero view."""
        return self.llm + self.compose * self.hero_views + self.clear + self.light * self.hero_views

    def per_room_with_levers(
        self, designs: int = 3, cleared_designs: int = 2, opened: int = 1
    ) -> float:
        """Three designs per room with the two levers: one cleared scene shared by the
        designs that replace furniture (Refresh keeps it), and the lighting pass only
        on the design the user opens (previews are composites)."""
        return (
            designs * (self.llm + self.compose * self.hero_views)
            + (self.clear if cleared_designs else 0.0)
            + opened * self.light * self.hero_views
        )

    def per_room_plain(self, designs: int = 3) -> float:
        return designs * self.plain()


def inr(usd: float) -> float:
    return usd * USD_TO_INR
