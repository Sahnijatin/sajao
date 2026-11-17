// Picks the keyframes the server measures and rebuilds from: the sharpest
// frame for each viewpoint, where a viewpoint is a place the phone stood and
// a direction it looked from there. Walking the room keeps adding keyframes
// that turning on one spot cannot, and time alone never adds one. Pure; the
// camera hands in candidates as it sees them.

export interface KeyframeCandidate {
  /** Local file of the full-resolution frame, kept until upload. */
  uri: string;
  /** Milliseconds from the start of the scan. */
  atMs: number;
  /** Variance of the Laplacian: higher is sharper. */
  sharpness: number;
  /** Where the phone pointed, degrees; null when the phone has no pose. */
  yaw: number | null;
  pitch: number | null;
  /** Where the phone stood on the floor plan, metres; missing or null without AR tracking. */
  x?: number | null;
  z?: number | null;
}

/** Side of a square of floor that counts as one place to stand. */
export const PLACE_CELL_M = 0.5;

/** Directions are grouped into cells this wide... */
export const YAW_CELL_DEGREES = 30;
/** ...and three bands: looking down, level, up. */
const PITCH_BANDS = [-20, 20];
/** Without a pose, one keyframe per this many milliseconds. */
export const TIME_CELL_MS = 1500;
/**
 * A frame with no measurable detail never becomes a keyframe. The sharpness
 * scale depends on the phone, the light and the room (a plain wall in a dim
 * room reads low while perfectly sharp), so there is no fixed bar for
 * "blurred": each cell keeps its sharpest frame instead, and a scan in a
 * plain or dim room still produces keyframes.
 */
export const MIN_SHARPNESS = 1;
/** A cell's keyframe is replaced only by a clearly sharper frame. */
const REPLACE_MARGIN = 1.1;
export const MAX_KEYFRAMES = 200;

export function cellOf(candidate: KeyframeCandidate): string {
  if (candidate.yaw === null || candidate.pitch === null) {
    return `t${Math.floor(candidate.atMs / TIME_CELL_MS)}`;
  }
  const turned = ((candidate.yaw % 360) + 360) % 360;
  const sector = Math.floor(turned / YAW_CELL_DEGREES);
  const band = PITCH_BANDS.filter((edge) => candidate.pitch! > edge).length;
  const direction = `d${sector}-${band}`;
  const { x, z } = candidate;
  if (typeof x !== "number" || typeof z !== "number") return direction;
  return `p${Math.floor(x / PLACE_CELL_M)}_${Math.floor(z / PLACE_CELL_M)}-${direction}`;
}

export type KeyframeSet = ReadonlyMap<string, KeyframeCandidate>;

export const NO_KEYFRAMES: KeyframeSet = new Map();

/** Offer one candidate; returns the new set (the old one is unchanged). */
export function offerKeyframe(set: KeyframeSet, candidate: KeyframeCandidate): KeyframeSet {
  if (!(candidate.sharpness >= MIN_SHARPNESS)) return set;
  const cell = cellOf(candidate);
  const current = set.get(cell);
  if (current && candidate.sharpness < current.sharpness * REPLACE_MARGIN) return set;
  if (!current && set.size >= MAX_KEYFRAMES) return set;
  const next = new Map(set);
  next.set(cell, candidate);
  return next;
}

/** Chosen keyframes in capture order. */
export function chosenKeyframes(set: KeyframeSet): KeyframeCandidate[] {
  return [...set.values()].sort((a, b) => a.atMs - b.atMs);
}

/** Candidates that lost their cell: their local files can be deleted. */
export function replacedBy(before: KeyframeSet, after: KeyframeSet): string[] {
  const kept = new Set([...after.values()].map((frame) => frame.uri));
  return [...before.values()].map((frame) => frame.uri).filter((uri) => !kept.has(uri));
}
