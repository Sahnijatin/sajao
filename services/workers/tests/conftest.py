"""Shared helpers for the workers tests."""

import math
from collections.abc import Callable

import numpy as np
import pytest


def room_points(
    length: float = 4.0,
    width: float = 3.0,
    height: float = 2.7,
    yaw_deg: float = 30.0,
    skip_wall: int | None = None,
    seed: int = 0,
) -> np.ndarray:
    """Points on the floor, ceiling and four walls of a box room in an AR world (y up)."""
    rng = np.random.default_rng(seed)
    n = 4000
    parts = [
        np.column_stack([rng.uniform(0, length, n), np.zeros(n), rng.uniform(0, width, n)]),
        np.column_stack([rng.uniform(0, length, n), np.full(n, height), rng.uniform(0, width, n)]),
    ]
    # Each wall: (start x, start z, end x, end z) on the floor.
    walls = [(0.0, 0.0, length, 0.0), (length, 0.0, length, width), (0.0, width, length, width)]
    walls.append((0.0, 0.0, 0.0, width))
    for i, (x0, z0, x1, z1) in enumerate(walls):
        if i == skip_wall:
            continue
        u, h = rng.uniform(0, 1, n), rng.uniform(0, height, n)
        parts.append(np.column_stack([x0 + u * (x1 - x0), h, z0 + u * (z1 - z0)]))
    points = np.concatenate(parts)
    points += rng.normal(0, 0.01, points.shape)
    # A few points seen through a doorway, far outside the room.
    points = np.concatenate([points, [[length + 3.0, 1.0, 1.0], [-2.5, 1.2, 2.0]]])
    theta = math.radians(yaw_deg)
    turn = np.array(
        [[math.cos(theta), 0, math.sin(theta)], [0, 1, 0], [-math.sin(theta), 0, math.cos(theta)]]
    )
    shifted: np.ndarray = points @ turn.T + np.array([1.5, -1.2, -2.0])  # floor 1.2 m below origin
    return shifted


@pytest.fixture
def room() -> Callable[..., np.ndarray]:
    """Builds depth points of a box room in an AR world (y up); see room_points."""
    return room_points
