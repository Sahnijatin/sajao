// Skia effect presets: the numbers behind the glows, the scan mesh, the
// canvas colour blobs, the grid and the paint sweep. Pure data and geometry,
// so the look is tested without a phone. The Skia components next to this
// file only draw what these functions describe.
import type { DeviceTier } from "../deviceTier";

/**
 * How much of an effect to draw.
 * full: blur, glow and motion. lite (low tier): no blur, simpler shapes.
 * still (reduced motion): the full look with no movement.
 */
export type EffectLevel = "full" | "lite" | "still";

export function effectLevel(theme: { tier: DeviceTier; reducedMotion: boolean }): EffectLevel {
  if (theme.tier === "low") return "lite";
  return theme.reducedMotion ? "still" : "full";
}

/** Whether an effect moves on its own. Low-tier effects stay still to save frames. */
export function isAnimated(level: EffectLevel): boolean {
  return level === "full";
}

// --- Glow --------------------------------------------------------------------

export const glow = {
  /** Soft halo behind a stroke or shape. */
  blurRadius: 2.2,
  accent: "#ad4f27",
  success: "#1fae55",
  warning: "#ff8a00",
} as const;

// --- Scan mesh ---------------------------------------------------------------

export const scanMesh = {
  edge: { color: "#8ff0ff", width: 0.9, opacity: 0.55 },
  /** Edges at the frontier, where the mesh is still forming. */
  edgeFaintOpacity: 0.08,
  face: { color: "#5ee0ff", opacity: 0.09 },
  point: { color: "#e9fdff", opacity: 0.9, radius: 1.6, radiusStrong: 2.8 },
  /** The white edge that sweeps across newly mapped surface. */
  sweep: {
    from: "rgba(94, 224, 255, 0)",
    mid: "rgba(94, 224, 255, 0.22)",
    to: "rgba(255, 255, 255, 0.55)",
  },
  glowBlurRadius: 2.2,
  /** Low tier: dots and edges only, slightly bolder because nothing glows. */
  lite: { edgeWidth: 1.2, edgeOpacity: 0.45, pointRadius: 2.2 },
} as const;

/** What the mesh draws at each level. Low tier: dots and edges, no faces, glow or sweep. */
export function scanMeshLayers(level: EffectLevel) {
  const lite = level === "lite";
  return { faces: !lite, glow: !lite, sweep: level === "full", edges: true, points: true };
}

// --- Canvas colour blobs -----------------------------------------------------

export interface Blob {
  /** Colour at the centre; it fades to transparent at 70% of the radius. */
  color: string;
  /** Resting centre, as a fraction of the canvas width and height. */
  x: number;
  y: number;
  /** Radius as a fraction of the canvas width. */
  radius: number;
  /** How far it drifts, as a fraction of the canvas width. */
  drift: number;
  /** Where in its loop it starts, 0 to 1, so the blobs do not move together. */
  phase: number;
}

export const canvasBlobs: readonly Blob[] = [
  { color: "rgba(173, 79, 39, 0.12)", x: 0.15, y: 0.12, radius: 0.55, drift: 0.06, phase: 0 },
  { color: "rgba(232, 178, 96, 0.20)", x: 0.9, y: 0.3, radius: 0.5, drift: 0.05, phase: 0.33 },
  { color: "rgba(176, 137, 104, 0.14)", x: 0.4, y: 0.85, radius: 0.6, drift: 0.07, phase: 0.66 },
];

/** One slow loop of the blob drift. */
export const BLOB_PERIOD_MS = 24_000;

/** Centre and radius of a blob in pixels at loop progress t (0 to 1). */
export function blobAt(blob: Blob, t: number, size: { width: number; height: number }) {
  "worklet";
  const angle = 2 * Math.PI * (t + blob.phase);
  return {
    cx: blob.x * size.width + Math.cos(angle) * blob.drift * size.width,
    cy: blob.y * size.height + Math.sin(angle) * blob.drift * size.width,
    r: blob.radius * size.width,
  };
}

// --- Perspective grid --------------------------------------------------------

export interface Segment {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

/**
 * A floor grid in one-point perspective: lines fan out from a vanishing
 * point on the horizon, and cross lines bunch up toward it.
 */
export function perspectiveGrid(options: {
  width: number;
  height: number;
  /** y of the far edge of the floor. */
  horizonY: number;
  columns: number;
  rows: number;
}): Segment[] {
  const { width, height, horizonY, columns, rows } = options;
  const depth = height - horizonY;
  // The far edge is narrower than the near edge.
  const farInset = width * 0.18;
  const segments: Segment[] = [];
  for (let column = 0; column <= columns; column += 1) {
    const t = column / columns;
    segments.push({
      x1: farInset + t * (width - 2 * farInset),
      y1: horizonY,
      x2: (t - 0.5) * width * 2.2 + width / 2,
      y2: height,
    });
  }
  for (let row = 1; row <= rows; row += 1) {
    // Squared spacing: rows get closer together toward the horizon.
    const t = (row / rows) ** 2;
    const y = horizonY + t * depth;
    const inset = farInset * (1 - t);
    segments.push({
      x1: inset - width * 0.6 * t,
      y1: y,
      x2: width - inset + width * 0.6 * t,
      y2: y,
    });
  }
  return segments;
}

// --- Paint sweep -------------------------------------------------------------

export const paintSweep = {
  durationMs: 600,
  /** Width of the bright roller edge leading the new colour. */
  edgeWidth: 14,
  edgeColor: "rgba(255, 255, 255, 0.55)",
} as const;

/**
 * The part of a wall already painted at progress 0 to 1, sweeping left to
 * right like a roller, plus the x of the leading edge.
 */
export function paintSweepAt(progress: number, wall: { x: number; width: number }) {
  "worklet";
  const clamped = Math.min(1, Math.max(0, progress));
  const painted = wall.width * clamped;
  return { x: wall.x, width: painted, edgeX: wall.x + painted };
}

/** Low tier and reduced motion: the colour changes at once. */
export function paintSweepDurationMs(level: EffectLevel): number {
  return level === "full" ? paintSweep.durationMs : 0;
}
