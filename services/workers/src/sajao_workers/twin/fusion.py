"""Merge per-frame object observations into 3D instances using voxel overlap.

Ported from the SJ-116 spike. Grouping uses the twin's own vocabulary: classes
that name the same physical thing (an armchair seen as a chair) may merge, and
the instance keeps the label with the highest total score.

Each observation is one 2D mask lifted to world points (from LiDAR or estimated
depth) and reduced to voxels. Observations of the same class that share enough
voxels become one instance; its box is fitted to voxels seen more than once.
"""

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from sajao_workers.twin.geometry import UprightBox, fit_upright_box

Voxel = tuple[int, int, int]
# Per voxel: point count and the sum of coordinates (for the centroid).
VoxelStats = tuple[int, float, float, float]


def voxelize(points: Iterable[Sequence[float]], voxel: float) -> dict[Voxel, VoxelStats]:
    out: dict[Voxel, list[float]] = {}
    for p in points:
        x, y, z = float(p[0]), float(p[1]), float(p[2])
        key = (math.floor(x / voxel), math.floor(y / voxel), math.floor(z / voxel))
        acc = out.setdefault(key, [0.0, 0.0, 0.0, 0.0])
        acc[0] += 1
        acc[1] += x
        acc[2] += y
        acc[3] += z
    return {k: (int(v[0]), v[1], v[2], v[3]) for k, v in out.items()}


@dataclass(frozen=True)
class Observation:
    frame: int
    label: str
    score: float
    voxels: dict[Voxel, VoxelStats]
    key: int = -1  # caller's id for the source mask, kept on the instance


@dataclass
class Instance:
    label: str
    labels: dict[str, float] = field(default_factory=dict)
    frames: set[int] = field(default_factory=set)
    hits: dict[Voxel, int] = field(default_factory=dict)
    sums: dict[Voxel, list[float]] = field(default_factory=dict)
    members: list[tuple[int, int]] = field(default_factory=list)

    def add(self, obs: Observation) -> None:
        self.frames.add(obs.frame)
        self.members.append((obs.frame, obs.key))
        self.labels[obs.label] = self.labels.get(obs.label, 0.0) + obs.score
        self.label = max(self.labels, key=lambda k: self.labels[k])
        for key, (n, sx, sy, sz) in obs.voxels.items():
            self.hits[key] = self.hits.get(key, 0) + 1
            acc = self.sums.setdefault(key, [0.0, 0.0, 0.0, 0.0])
            acc[0] += n
            acc[1] += sx
            acc[2] += sy
            acc[3] += sz

    def overlap(self, obs: Observation) -> float:
        if not obs.voxels or not self.hits:
            return 0.0
        shared = sum(1 for k in obs.voxels if k in self.hits)
        return shared / min(len(obs.voxels), len(self.hits))

    def core_points(self, min_hits: int) -> list[tuple[float, float, float]]:
        """Centroids of voxels seen in at least `min_hits` observations."""
        pts = []
        for key, h in self.hits.items():
            if h >= min_hits:
                n, sx, sy, sz = self.sums[key]
                pts.append((sx / n, sy / n, sz / n))
        return pts


# Vocabulary classes that may name the same object from different views.
GROUPS = {
    "armchair": "chair",
    "stool": "chair",
    "ottoman": "chair",
    "desk": "table",
    "nightstand": "cabinet",
    "wardrobe": "cabinet",
    "shelf": "cabinet",
}


def _group(label: str) -> str:
    key = label.lower().strip()
    return GROUPS.get(key, key)


def fuse(observations: Iterable[Observation], min_overlap: float = 0.2) -> list[Instance]:
    instances: list[Instance] = []
    for obs in observations:
        best, best_overlap = None, 0.0
        for inst in instances:
            if _group(inst.label) != _group(obs.label):
                continue
            ov = inst.overlap(obs)
            if ov > best_overlap:
                best, best_overlap = inst, ov
        if best is not None and best_overlap >= min_overlap:
            best.add(obs)
        else:
            inst = Instance(label=obs.label)
            inst.add(obs)
            instances.append(inst)
    return instances


def merge_instances(instances: Iterable[Instance], min_overlap: float = 0.3) -> list[Instance]:
    """Merge same-class instances whose voxels overlap, until none do.

    Per-frame fusion can split one object into several instances when early
    views see different parts; this second pass joins them.
    """
    pool = list(instances)
    merged = True
    while merged:
        merged = False
        for i in range(len(pool)):
            for j in range(i + 1, len(pool)):
                a, b = pool[i], pool[j]
                if _group(a.label) != _group(b.label):
                    continue
                shared = sum(1 for k in b.hits if k in a.hits)
                if shared / max(1, min(len(a.hits), len(b.hits))) < min_overlap:
                    continue
                _absorb(a, b)
                del pool[j]
                merged = True
                break
            if merged:
                break
    return pool


def _absorb(a: Instance, b: Instance) -> None:
    a.frames |= b.frames
    a.members.extend(b.members)
    for lab, sc in b.labels.items():
        a.labels[lab] = a.labels.get(lab, 0.0) + sc
    a.label = max(a.labels, key=lambda k: a.labels[k])
    for key, h in b.hits.items():
        a.hits[key] = a.hits.get(key, 0) + h
        acc = a.sums.setdefault(key, [0.0, 0.0, 0.0, 0.0])
        for i, v in enumerate(b.sums[key]):
            acc[i] += v


def instance_boxes(
    instances: Iterable[Instance],
    up_axis: int,
    min_frames: int = 3,
    min_hit_ratio: float = 0.15,
    min_points: int = 8,
) -> list[tuple[str, UprightBox, int]]:
    """Boxes for instances seen in enough frames: (label, box, frames seen)."""
    out = []
    for inst in instances:
        n = len(inst.frames)
        if n < min_frames:
            continue
        min_hits = max(2, math.ceil(min_hit_ratio * n))
        pts = inst.core_points(min_hits)
        if len(pts) < min_points:
            continue
        out.append((inst.label, fit_upright_box(pts, up_axis), n))
    return out
