"""A mask's outline on its photo: closed polygons in shares of the photo's size.

The app draws a tapped object's outline from these, without the mask file. Pure
numpy: the mask is reduced to at most TRACE_SIZE pixels on its long side, each
part bigger than MIN_PART_SHARE of the photo is traced along its outer edge
(Moore neighbours), and the trace is simplified (Douglas-Peucker) to within
TOLERANCE of the photo's width and at most MAX_POINTS points.
"""

from collections import deque

import numpy as np

TRACE_SIZE = 320
MIN_PART_SHARE = 0.002
MAX_PARTS = 8
MAX_POINTS = 128
TOLERANCE = 0.003

# Moore neighbourhood, clockwise from west (image rows grow downward).
_STEPS = ((0, -1), (-1, -1), (-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1))


def _shrink(mask: np.ndarray) -> np.ndarray:
    h, w = mask.shape
    scale = TRACE_SIZE / max(h, w)
    if scale >= 1:
        return mask
    rows = np.minimum((np.arange(round(h * scale)) / scale).astype(int), h - 1)
    cols = np.minimum((np.arange(round(w * scale)) / scale).astype(int), w - 1)
    small: np.ndarray = mask[rows][:, cols]
    return small


def _parts(mask: np.ndarray) -> list[np.ndarray]:
    """Connected parts (8-neighbour) as boolean masks, largest first."""
    labels = np.zeros(mask.shape, dtype=np.int32)
    sizes: list[int] = []
    h, w = mask.shape
    for start in zip(*np.nonzero(mask), strict=True):
        if labels[start]:
            continue
        label = len(sizes) + 1
        labels[start] = label
        queue, size = deque([start]), 0
        while queue:
            y, x = queue.popleft()
            size += 1
            for dy, dx in _STEPS:
                ny, nx = y + dy, x + dx
                if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not labels[ny, nx]:
                    labels[ny, nx] = label
                    queue.append((ny, nx))
        sizes.append(size)
    order = np.argsort(sizes)[::-1]
    return [labels == i + 1 for i in order]


def _trace(part: np.ndarray) -> list[tuple[int, int]]:
    """The outer boundary of one part, as (row, col) pixel corners in order."""
    padded = np.pad(part, 1)
    ys, xs = np.nonzero(padded)
    first = int(np.argmin(ys * padded.shape[1] + xs))
    start = (int(ys[first]), int(xs[first]))
    boundary = [start]
    current, came_from = start, 0  # entered from the west
    for _ in range(4 * part.size):
        for k in range(8):
            d = (came_from + k) % 8
            ny, nx = current[0] + _STEPS[d][0], current[1] + _STEPS[d][1]
            if padded[ny, nx]:
                came_from = (d + 5) % 8  # back two steps from the reverse direction
                current = (ny, nx)
                break
        else:
            break  # a single pixel
        if current == start:
            break
        boundary.append(current)
    return [(y - 1, x - 1) for y, x in boundary]


def _simplify(points: np.ndarray, tolerance: float) -> np.ndarray:
    """Douglas-Peucker on an open polyline."""
    if len(points) < 3:
        return points
    a, b = points[0], points[-1]
    ab = b - a
    norm = np.hypot(*ab)
    rel = points - a
    if norm < 1e-9:
        distances = np.hypot(rel[:, 0], rel[:, 1])
    else:
        distances = np.abs(ab[0] * rel[:, 1] - ab[1] * rel[:, 0]) / norm
    i = int(np.argmax(distances))
    if distances[i] <= tolerance:
        return np.stack([a, b])
    left = _simplify(points[: i + 1], tolerance)
    right = _simplify(points[i:], tolerance)
    return np.concatenate([left[:-1], right])


def _closed(points: np.ndarray, tolerance: float) -> np.ndarray:
    """Simplify a closed ring: split at the point farthest from the first."""
    far = int(np.argmax(np.hypot(*(points - points[0]).T)))
    one = _simplify(points[: far + 1], tolerance)
    two = _simplify(np.concatenate([points[far:], points[:1]]), tolerance)
    ring: np.ndarray = np.concatenate([one[:-1], two[:-1]])
    return ring


def outline(mask: np.ndarray) -> list[list[dict[str, float]]]:
    """Outer edges of a mask as polygons of {"x", "y"} shares of its width and height,
    largest part first. Empty when nothing is big enough to draw."""
    small = _shrink(np.asarray(mask, dtype=bool))
    h, w = small.shape
    polygons: list[list[dict[str, float]]] = []
    for part in _parts(small)[:MAX_PARTS]:
        if part.sum() < MIN_PART_SHARE * h * w:
            break
        trace = np.asarray(_trace(part), dtype=np.float64)
        if len(trace) < 3:
            continue
        # Pixel centres to shares; nudge outward by half a pixel is not needed at this scale.
        tolerance = TOLERANCE * w
        ring = _closed(trace, tolerance)
        while len(ring) > MAX_POINTS:
            tolerance *= 1.5
            ring = _closed(trace, tolerance)
        if len(ring) < 3:
            continue
        polygons.append(
            [
                {
                    "x": round(float(np.clip((x + 0.5) / w, 0, 1)), 4),
                    "y": round(float(np.clip((y + 0.5) / h, 0, 1)), 4),
                }
                for y, x in ring
            ]
        )
    return polygons
