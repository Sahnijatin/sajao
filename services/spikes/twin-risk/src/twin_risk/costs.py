"""GPU cost and streaming arithmetic for the spike report.

Prices are Modal's published per-second list prices, pinned here so the report
can be recomputed. Update them together with a rerun.
"""

from __future__ import annotations

GPU_USD_PER_SECOND: dict[str, float] = {
    "T4": 0.000164,
    "L4": 0.000222,
    "A10G": 0.000306,
    "L40S": 0.000542,
    "A100-40GB": 0.000583,
    "A100-80GB": 0.000694,
    "H100": 0.001097,
}
CPU_CORE_USD_PER_SECOND = 0.0000131
MEMORY_GIB_USD_PER_SECOND = 0.00000222


def gpu_cost_usd(gpu: str, seconds: float) -> float:
    if seconds < 0:
        raise ValueError("seconds must be non-negative")
    return GPU_USD_PER_SECOND[gpu] * seconds


def cpu_cost_usd(cores: float, memory_gib: float, seconds: float) -> float:
    if seconds < 0:
        raise ValueError("seconds must be non-negative")
    return (cores * CPU_CORE_USD_PER_SECOND + memory_gib * MEMORY_GIB_USD_PER_SECOND) * seconds


def stream_gpu_cost_per_minute(gpu: str, render_ms_per_frame: float, fps: float) -> float:
    """GPU cost of one minute of server-rendered viewing for one user.

    Assumes a GPU renders only for that user and is billed for the share of
    each second spent rendering (at least that share; idle time costs extra
    unless sessions are packed onto one GPU).
    """
    busy_fraction = min(1.0, render_ms_per_frame * fps / 1000.0)
    return GPU_USD_PER_SECOND[gpu] * 60.0 * busy_fraction


def bitrate_mbps(num_bytes: int, seconds: float) -> float:
    if seconds <= 0:
        raise ValueError("seconds must be positive")
    return num_bytes * 8.0 / seconds / 1e6


def usd_to_inr(usd: float, rate: float = 88.0) -> float:
    """Approximate rupee figure for the report; the rate is a stated assumption."""
    return usd * rate
