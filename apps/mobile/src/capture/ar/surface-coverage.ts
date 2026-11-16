// Coverage for the AR scan, counted on the room's surfaces instead of the
// directions the phone pointed. A few times a second the AR view casts a
// small grid of rays into the planes it has found and reports where each ray
// landed: a wall or the floor. Walls and floor are split into cells; a cell
// counts once two accepted samples have landed in it. A sample is accepted
// only when tracking is normal, the phone turns slower than 30 degrees a
// second and the frame is sharp, so spinning in place or waving the phone
// earns nothing.
//
// This is guidance for the person scanning, not a measurement: it never sets
// a dimension.

/** Turning faster than this blurs AR frames; such samples do not count. A slow pan is 20 to 40. */
export const MAX_TURN_DEG_PER_S = 45;
/** Cell size on walls and floor, in metres. */
export const CELL_M = 0.5;
/** Accepted samples a cell needs before it counts as mapped. */
export const HITS_PER_CELL = 2;
/** Walls closer than this in direction (degrees) and offset (metres) are one wall. */
export const SAME_WALL_DEGREES = 25;
export const SAME_WALL_OFFSET_M = 0.35;
/** Wall cells counted between these heights above the floor: what furniture stands against. */
export const WALL_BAND_M = { from: 0, to: 2.0 };
/**
 * AR world height 0 is where the phone started, not the floor. Until a floor
 * plane is found, assume the phone started at about chest height.
 */
export const ASSUMED_START_HEIGHT_M = 1.4;
/** A wall is done at this many mapped cells, or fewer when it is narrower. */
export const WALL_TARGET_CELLS = 12;
/** The floor is done at this many mapped cells (4 square metres). */
export const FLOOR_TARGET_CELLS = 16;
/** Walls that make a full scan: standing in a doorway you face three. */
export const WALLS_FOR_FULL = 3;
/** A frame is blurred when its sharpness is under this share of the session's recent best. */
export const SHARP_SHARE = 0.45;
/** Recent sharpness readings kept to judge what "sharp" means on this phone and in this light. */
const SHARPNESS_WINDOW = 40;
/** Recent samples kept to decide whether to ask the person to slow down. */
const RECENT_SAMPLES = 6;
/** Ask to slow down once this many of the recent samples were rejected. */
export const SLOW_DOWN_AFTER = 3;

export interface SurfaceHit {
  kind: "wall" | "floor";
  /** Wall only: direction the wall faces, degrees about the vertical axis. */
  normalYaw: number;
  /** Wall only: the wall's distance from the world origin along its normal, in metres. */
  offset: number;
  x: number;
  y: number;
  z: number;
}

export interface SurfaceSample {
  /** Sharpness of the camera frame the rays were cast from; any scale, compared within a session. */
  sharpness: number;
  hits: readonly SurfaceHit[];
  /** World height of the floor plane, when one has been found. */
  floorY?: number | null;
}

export interface Wall {
  normalYaw: number;
  offset: number;
  /** Accepted hits per cell, keyed "along,up". */
  cells: Readonly<Record<string, number>>;
  /** Along-wall cell range seen in any sample, accepted or not: how wide the wall is so far. */
  minAlong: number;
  maxAlong: number;
}

export type RejectCause = "turning" | "blurred" | "tracking";

export interface SurfaceCoverage {
  walls: readonly Wall[];
  floor: Readonly<Record<string, number>>;
  sharpness: readonly number[];
  /** Newest last: null for an accepted sample, else why it was rejected. */
  recent: readonly (RejectCause | null)[];
  accepted: number;
  rejected: number;
}

export const EMPTY_SURFACE_COVERAGE: SurfaceCoverage = {
  walls: [],
  floor: {},
  sharpness: [],
  recent: [],
  accepted: 0,
  rejected: 0,
};

function angleBetween(a: number, b: number): number {
  const d = Math.abs(((((a - b) % 360) + 540) % 360) - 180);
  return d;
}

/** Position along a wall, in metres: across the wall's face, left to right as you face it. */
function alongWall(hit: SurfaceHit, normalYaw: number): number {
  const r = (normalYaw * Math.PI) / 180;
  // The normal is (sin r, 0, cos r); the tangent is (cos r, 0, -sin r).
  return hit.x * Math.cos(r) - hit.z * Math.sin(r);
}

const cellOf = (metres: number) => Math.floor(metres / CELL_M);

function findWall(walls: readonly Wall[], hit: SurfaceHit): number {
  return walls.findIndex(
    (wall) =>
      angleBetween(wall.normalYaw, hit.normalYaw) <= SAME_WALL_DEGREES &&
      Math.abs(wall.offset - hit.offset) <= SAME_WALL_OFFSET_M,
  );
}

/** True when a frame is sharp against the same session's recent frames. Shared with the 2D scan. */
export function sharpEnough(history: readonly number[], sharpness: number): boolean {
  // Too few readings to know this phone's normal: accept.
  if (history.length < 5) return true;
  const sorted = [...history].sort((a, b) => a - b);
  const best = sorted[Math.floor(sorted.length * 0.8)] ?? sharpness;
  return sharpness >= best * SHARP_SHARE;
}

/** Why a sample cannot count, or null when it can. */
export function rejectSample(
  coverage: SurfaceCoverage,
  sample: SurfaceSample,
  turnDegPerS: number,
  trackingNormal: boolean,
): RejectCause | null {
  if (!trackingNormal) return "tracking";
  if (turnDegPerS > MAX_TURN_DEG_PER_S) return "turning";
  if (!sharpEnough(coverage.sharpness, sample.sharpness)) return "blurred";
  return null;
}

/** Fold one sample in. Pure: returns a new state. */
export function addSurfaceSample(
  coverage: SurfaceCoverage,
  sample: SurfaceSample,
  turnDegPerS: number,
  trackingNormal: boolean,
): SurfaceCoverage {
  const cause = rejectSample(coverage, sample, turnDegPerS, trackingNormal);
  const accepted = cause === null;
  const walls = coverage.walls.map((wall) => ({ ...wall, cells: { ...wall.cells } }));
  const floor = { ...coverage.floor };
  const floorY = sample.floorY ?? -ASSUMED_START_HEIGHT_M;

  for (const hit of sample.hits) {
    if (hit.kind === "floor") {
      if (!accepted) continue;
      const key = `${cellOf(hit.x)},${cellOf(hit.z)}`;
      floor[key] = (floor[key] ?? 0) + 1;
      continue;
    }
    let index = findWall(walls, hit);
    if (index < 0) {
      walls.push({
        normalYaw: hit.normalYaw,
        offset: hit.offset,
        cells: {},
        minAlong: Infinity,
        maxAlong: -Infinity,
      });
      index = walls.length - 1;
    }
    const wall = walls[index];
    if (!wall) continue;
    const along = cellOf(alongWall(hit, wall.normalYaw));
    // Width counts every sighting, so a quick look reveals how much is left to cover.
    wall.minAlong = Math.min(wall.minAlong, along);
    wall.maxAlong = Math.max(wall.maxAlong, along);
    const height = hit.y - floorY;
    if (!accepted || height < WALL_BAND_M.from || height > WALL_BAND_M.to) continue;
    const key = `${along},${cellOf(height)}`;
    wall.cells[key] = (wall.cells[key] ?? 0) + 1;
  }

  const sharpness =
    cause === "tracking" || !Number.isFinite(sample.sharpness)
      ? coverage.sharpness
      : [...coverage.sharpness, sample.sharpness].slice(-SHARPNESS_WINDOW);
  return {
    walls,
    floor,
    sharpness,
    recent: pushRecent(coverage.recent, cause),
    accepted: coverage.accepted + (accepted ? 1 : 0),
    rejected: coverage.rejected + (accepted ? 0 : 1),
  };
}

const mappedCells = (cells: Readonly<Record<string, number>>) =>
  Object.values(cells).filter((hits) => hits >= HITS_PER_CELL).length;

/** 0 to 1 for one wall: mapped cells against what its width so far can hold. */
export function wallProgress(wall: Wall): number {
  const width = wall.maxAlong >= wall.minAlong ? wall.maxAlong - wall.minAlong + 1 : 0;
  const rows = Math.ceil((WALL_BAND_M.to - WALL_BAND_M.from) / CELL_M);
  const target = Math.max(4, Math.min(WALL_TARGET_CELLS, width * rows));
  return Math.min(1, mappedCells(wall.cells) / target);
}

export function floorProgress(coverage: SurfaceCoverage): number {
  return Math.min(1, mappedCells(coverage.floor) / FLOOR_TARGET_CELLS);
}

/** 0 to 1: the three best-covered walls and the floor, weighted equally. */
export function surfaceFraction(coverage: SurfaceCoverage): number {
  const walls = coverage.walls
    .map(wallProgress)
    .sort((a, b) => b - a)
    .slice(0, WALLS_FOR_FULL);
  const sum = walls.reduce((total, progress) => total + progress, 0) + floorProgress(coverage);
  return sum / (WALLS_FOR_FULL + 1);
}

/** True when enough recent samples were rejected for moving fast or blur. */
export function shouldSlowDown(coverage: SurfaceCoverage): boolean {
  return tooManyRejected(coverage.recent);
}

/** Enough of the recent samples or frames were rejected for turning fast or blur. */
export function tooManyRejected(recent: readonly (RejectCause | null)[]): boolean {
  return (
    recent.filter((cause) => cause === "turning" || cause === "blurred").length >= SLOW_DOWN_AFTER
  );
}

/** Keep the most recent causes, newest last. */
export function pushRecent(
  recent: readonly (RejectCause | null)[],
  cause: RejectCause | null,
): (RejectCause | null)[] {
  return [...recent, cause].slice(-RECENT_SAMPLES);
}
