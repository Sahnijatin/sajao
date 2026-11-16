// Coverage for the simple scan, counted from how the camera turned and
// moved, never from planes or the detector. Two parts:
//
// - Heading: the circle around the person is split into sectors; a sector
//   counts once the camera has faced it for about half a second while
//   turning slowly, holding steady and seeing a sharp picture.
// - Movement: metres walked, from AR poses. Walking gives the server the
//   parallax it needs to rebuild the room, and gives the phone's own
//   tracking the same. A phone whose AR never tracks earns this part from
//   steady scanning time instead.
//
// Spinning fast, shaking or pointing at the floor earns nothing. This is
// guidance for the person scanning, not a measurement: it never sets a
// dimension.
import { addSweep, type CoverageState, EMPTY_COVERAGE, mappedDegrees } from "./coverage";
import type { Point2 } from "./ar/guidance";
import { MAX_TURN_DEG_PER_S, pushRecent, type RejectCause } from "./ar/surface-coverage";

/** Turning through this much is a full heading sweep: most of a room from inside it. */
export const HEADING_TARGET_DEGREES = 270;
/** Walking this far is the full movement share. */
export const MOVE_TARGET_M = 3;
/** Steady samples that stand in for walking when AR never tracks (about 25 s). */
export const STEADY_TARGET_SAMPLES = 250;
/** Heading and movement shares of the whole. */
export const HEADING_WEIGHT = 0.7;
export const MOVE_WEIGHT = 0.3;
/** Pointing further than this above or below the horizon sees ceiling or floor, not the room. */
export const MAX_PITCH_DEGREES = 60;
/** Steps shorter than this are tracking jitter; longer ones are a tracking jump. */
export const MIN_STEP_M = 0.02;
export const MAX_STEP_M = 0.5;
/** Samples closer together than this are one sample, so a faster pose stream earns no more. */
export const SAMPLE_INTERVAL_MS = 90;
/** Done is offered at this share; the hint asks for a bit more until 100%. */
export const MOTION_DONE_SHARE = 0.7;
/** Accepted samples needed before Done, on top of the share (about 5 s of steady scanning). */
export const MIN_ACCEPTED_SAMPLES = 50;
/** "Walk around" shows once this much heading is covered with less than this walked. */
export const WALK_HINT_HEADING_SHARE = 0.5;
export const WALK_HINT_BELOW_M = 1;

export interface MotionSampleInput {
  /** Where the camera points, degrees. */
  yaw: number;
  pitch: number;
  /** How fast the camera turns, degrees per second. */
  turnDegPerS: number;
  /** The motion guardrail is good and the scan is not paused. */
  steady: boolean;
  /** The latest camera frame is sharp against this scan's recent frames. */
  sharp: boolean;
  /** Camera position on the floor plan from AR tracking; null while AR is not tracking. */
  position: Point2 | null;
  atMs: number;
}

export interface MotionCoverage {
  headings: CoverageState;
  /** Metres walked, from AR positions on accepted samples. */
  pathM: number;
  lastPosition: Point2 | null;
  /** AR has reported a position at least once. */
  tracked: boolean;
  accepted: number;
  rejected: number;
  /** Newest last: null for an accepted sample, else why it was rejected. */
  recent: readonly (RejectCause | null)[];
  lastSampleMs: number | null;
}

export const EMPTY_MOTION_COVERAGE: MotionCoverage = {
  headings: EMPTY_COVERAGE,
  pathM: 0,
  lastPosition: null,
  tracked: false,
  accepted: 0,
  rejected: 0,
  recent: [],
  lastSampleMs: null,
};

/** Why a sample cannot count, or null when it can. */
export function rejectMotionSample(sample: MotionSampleInput): RejectCause | null {
  if (sample.turnDegPerS > MAX_TURN_DEG_PER_S) return "turning";
  if (!sample.steady || !sample.sharp) return "blurred";
  return null;
}

/** Fold one sample in. Pure: returns a new state. */
export function addMotionSample(
  coverage: MotionCoverage,
  sample: MotionSampleInput,
): MotionCoverage {
  if (
    coverage.lastSampleMs !== null &&
    sample.atMs - coverage.lastSampleMs >= 0 &&
    sample.atMs - coverage.lastSampleMs < SAMPLE_INTERVAL_MS
  ) {
    return coverage;
  }
  const cause = rejectMotionSample(sample);
  const accepted = cause === null;
  let pathM = coverage.pathM;
  let lastPosition = coverage.lastPosition;
  if (sample.position) {
    const step = lastPosition
      ? Math.hypot(sample.position.x - lastPosition.x, sample.position.z - lastPosition.z)
      : Infinity;
    if (step >= MIN_STEP_M) {
      // A jump is tracking finding itself again, not a step; the walk restarts from there.
      if (accepted && step <= MAX_STEP_M) pathM += step;
      lastPosition = sample.position;
    }
  }
  const level = Math.abs(sample.pitch) <= MAX_PITCH_DEGREES;
  return {
    headings: accepted && level ? addSweep(coverage.headings, sample.yaw) : coverage.headings,
    pathM,
    lastPosition,
    tracked: coverage.tracked || sample.position !== null,
    accepted: coverage.accepted + (accepted ? 1 : 0),
    rejected: coverage.rejected + (accepted ? 0 : 1),
    recent: pushRecent(coverage.recent, cause),
    lastSampleMs: sample.atMs,
  };
}

/** 0 to 1: how much of the heading sweep is covered. */
export function headingShare(coverage: MotionCoverage): number {
  return Math.min(1, mappedDegrees(coverage.headings) / HEADING_TARGET_DEGREES);
}

/** 0 to 1: metres walked, or steady scanning time on a phone whose AR never tracked. */
export function moveShare(coverage: MotionCoverage): number {
  return Math.min(
    1,
    coverage.tracked ? coverage.pathM / MOVE_TARGET_M : coverage.accepted / STEADY_TARGET_SAMPLES,
  );
}

/** 0 to 1, shown on the progress ring. */
export function motionFraction(coverage: MotionCoverage): number {
  return HEADING_WEIGHT * headingShare(coverage) + MOVE_WEIGHT * moveShare(coverage);
}

export function motionDone(coverage: MotionCoverage): boolean {
  return (
    motionFraction(coverage) >= MOTION_DONE_SHARE - 1e-9 &&
    coverage.accepted >= MIN_ACCEPTED_SAMPLES
  );
}

/** Enough heading is covered but the person has stood on one spot. */
export function shouldWalk(coverage: MotionCoverage): boolean {
  return (
    coverage.tracked &&
    headingShare(coverage) >= WALK_HINT_HEADING_SHARE &&
    coverage.pathM < WALK_HINT_BELOW_M
  );
}
