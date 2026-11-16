// Keeps the scan mesh steady from frame to frame. Raw feature points jump
// around; the tracker remembers points on a screen grid, lets them fade in,
// and forgets ones that stop being seen, so the mesh spreads instead of
// flickering.
import type { FeaturePoint } from "./feature-points";
import { type Point, type Triangle, triangulate } from "./triangulate";

export interface TrackedPoint extends Point {
  strength: number;
  /** 0 when first seen, rising to 1: new points fade in at the frontier. */
  confidence: number;
}

export interface MeshState {
  points: TrackedPoint[];
  triangles: Triangle[];
  /** Share of the screen grid that has mapped points, 0 to 1. */
  coverage: number;
}

export interface TrackerOptions {
  /** The screen is divided into this many columns and rows; one point per cell. */
  columns: number;
  rows: number;
  maxPoints: number;
  /** Confidence gained each time a point is seen again. */
  gain: number;
  /** Confidence lost each frame a point is not seen. */
  decay: number;
}

export const DEFAULT_TRACKER_OPTIONS: TrackerOptions = {
  columns: 12,
  rows: 20,
  maxPoints: 140,
  gain: 0.25,
  decay: 0.04,
};

/** Low-tier phones track fewer points: dots and edges, and less work per frame. */
export const LOW_TIER_TRACKER_OPTIONS: TrackerOptions = {
  ...DEFAULT_TRACKER_OPTIONS,
  columns: 8,
  rows: 14,
  maxPoints: 60,
};

export const EMPTY_MESH: MeshState = { points: [], triangles: [], coverage: 0 };

interface Cell extends TrackedPoint {
  cell: number;
}

/** Fold one frame's feature points into the mesh. Pure: returns a new state. */
export function updateMesh(
  previous: MeshState,
  seen: readonly FeaturePoint[],
  options: TrackerOptions = DEFAULT_TRACKER_OPTIONS,
): MeshState {
  "worklet";
  const { columns, rows, maxPoints, gain, decay } = options;
  const cellOf = (point: Point) =>
    Math.min(rows - 1, Math.max(0, Math.floor(point.y * rows))) * columns +
    Math.min(columns - 1, Math.max(0, Math.floor(point.x * columns)));

  const cells = new Map<number, Cell>();
  for (const point of previous.points) {
    cells.set(cellOf(point), {
      ...point,
      cell: cellOf(point),
      confidence: point.confidence - decay,
    });
  }
  for (const point of seen) {
    const cell = cellOf(point);
    const known = cells.get(cell);
    if (known) {
      // Seen again: undo this frame's decay, grow, and ease toward the new position.
      known.confidence = Math.min(1, known.confidence + decay + gain);
      known.x += (point.x - known.x) * 0.3;
      known.y += (point.y - known.y) * 0.3;
      known.strength = Math.max(known.strength, point.strength);
    } else {
      cells.set(cell, { x: point.x, y: point.y, strength: point.strength, confidence: gain, cell });
    }
  }

  const points = [...cells.values()]
    .filter((point) => point.confidence > 0)
    .sort((a, b) => b.confidence - a.confidence || a.cell - b.cell)
    .slice(0, maxPoints)
    .sort((a, b) => a.cell - b.cell)
    .map(({ cell: _cell, ...point }) => point);

  return {
    points,
    triangles: triangulate(points),
    coverage: points.length / Math.min(maxPoints, columns * rows),
  };
}

/** Points in screen pixels, for drawing. */
export function toScreen(mesh: MeshState, size: { width: number; height: number }): Point[] {
  return mesh.points.map((point) => ({ x: point.x * size.width, y: point.y * size.height }));
}
