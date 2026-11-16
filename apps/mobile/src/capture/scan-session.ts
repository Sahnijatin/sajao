// The whole state of a scan, advanced by events: an analysed frame, a
// motion sensor reading, a camera exposure reading, or the user choosing to
// scan anyway. Pure, so the behaviour of the capture screen is tested
// without a camera.
//
// Guardrails are judged on every event: light from frames, steady and level
// from the motion sensors, so a chip changes as soon as its signal does.
import {
  addFrame,
  addSweep,
  type CoverageState,
  coverageFraction,
  EMPTY_COVERAGE,
  enoughCoverage,
} from "./coverage";
import type { FeaturePoint } from "./feature-points";
import type { FrameStats } from "./frame-stats";
import {
  ALL_GOOD,
  evaluateGuardrails,
  type GuardrailState,
  NOT_PAUSED,
  type PauseState,
  type ScanReading,
  scanAnyway,
  shouldUseFrame,
  updatePause,
} from "./guardrails";
import {
  DEFAULT_TRACKER_OPTIONS,
  EMPTY_MESH,
  LOW_TIER_TRACKER_OPTIONS,
  type MeshState,
  shiftMesh,
  updateMesh,
} from "./mesh-tracker";
import { type MotionSample, wrapDegrees } from "./pose";

export interface ScanState {
  mesh: MeshState;
  guardrails: GuardrailState;
  pause: PauseState;
  /** The latest analysed frame's measurements; null before the first frame. */
  frame: { stats: FrameStats; aspect: number; featureCount: number } | null;
  /** Smoothed motion readings. */
  motion: Pick<MotionSample, "rotationRate" | "acceleration" | "rollDegrees" | "pitchDegrees">;
  isoRatio: number;
  /** Where the phone points, integrated from the gyroscope, in degrees. */
  pose: { yaw: number; pitch: number };
  /** The pose when the mesh was last updated, to move it with the view. */
  meshPose: { yaw: number; pitch: number };
  coverage: CoverageState;
  hasGyro: boolean;
  /** Time of the last event and of the last motion reading, in ms. */
  clockMs: number | null;
  motionMs: number | null;
  /** Frames that were good enough to use, so far. */
  usableFrames: number;
}

export const INITIAL_SCAN: ScanState = {
  mesh: EMPTY_MESH,
  guardrails: ALL_GOOD,
  pause: NOT_PAUSED,
  frame: null,
  motion: { rotationRate: 0, acceleration: 0, rollDegrees: 0, pitchDegrees: 0 },
  isoRatio: 0,
  pose: { yaw: 0, pitch: 0 },
  meshPose: { yaw: 0, pitch: 0 },
  coverage: EMPTY_COVERAGE,
  hasGyro: false,
  clockMs: null,
  motionMs: null,
  usableFrames: 0,
};

export type ScanEvent =
  | {
      type: "frame";
      stats: FrameStats;
      points: FeaturePoint[];
      /** Width over height of the upright frame. */
      aspect: number;
      atMs: number;
    }
  | { type: "motion"; sample: MotionSample; atMs: number }
  | { type: "exposure"; isoRatio: number }
  | { type: "scanAnyway" }
  | { type: "reset" };

/** Weight of a new motion reading against the running value: steadies the chip. */
const MOTION_SMOOTHING = 0.5;
/** A gap longer than this (app in background) does not count as time spent failing. */
const MAX_STEP_MS = 1000;
/** The long side of a phone's main camera frame spans about this many degrees. */
const LONG_SIDE_FOV_DEGREES = 65;

/** Degrees the upright frame spans across and down, for a given width over height. */
export function frameFov(aspect: number): { across: number; down: number } {
  const halfLong = (LONG_SIDE_FOV_DEGREES / 2) * (Math.PI / 180);
  const shortSide =
    (2 * Math.atan(Math.tan(halfLong) * Math.min(aspect, 1 / aspect)) * 180) / Math.PI;
  return aspect <= 1
    ? { across: shortSide, down: LONG_SIDE_FOV_DEGREES }
    : { across: LONG_SIDE_FOV_DEGREES, down: shortSide };
}

function reading(state: ScanState): ScanReading {
  // Before the first frame, light and glare stay as they are.
  const stats = state.frame?.stats ?? { brightness: 255, glare: 0, sharpness: 0 };
  return { ...stats, ...state.motion, isoRatio: state.isoRatio };
}

function stepMs(state: ScanState, atMs: number): number {
  if (state.clockMs === null) return 0;
  return Math.min(MAX_STEP_MS, Math.max(0, atMs - state.clockMs));
}

/** Re-judge the guardrails and the pause after any new reading. */
function judge(state: ScanState, elapsedMs: number): ScanState {
  const guardrails = evaluateGuardrails(state.guardrails, reading(state));
  const pause = updatePause(state.pause, guardrails, elapsedMs);
  return { ...state, guardrails, pause };
}

export function scanReducer(tier: "standard" | "low") {
  const tracker = tier === "low" ? LOW_TIER_TRACKER_OPTIONS : DEFAULT_TRACKER_OPTIONS;
  return (state: ScanState, event: ScanEvent): ScanState => {
    switch (event.type) {
      case "reset":
        return INITIAL_SCAN;
      case "scanAnyway":
        return { ...state, pause: scanAnyway(state.pause) };
      case "exposure":
        return judge({ ...state, isoRatio: event.isoRatio }, 0);
      case "motion": {
        const { sample, atMs } = event;
        const dtSeconds =
          state.motionMs === null
            ? 0
            : Math.min(MAX_STEP_MS, Math.max(0, atMs - state.motionMs)) / 1000;
        const smooth = (previous: number, next: number) =>
          previous + (next - previous) * MOTION_SMOOTHING;
        const next: ScanState = {
          ...state,
          motion: {
            rotationRate: smooth(state.motion.rotationRate, sample.rotationRate),
            acceleration: smooth(state.motion.acceleration, sample.acceleration),
            rollDegrees: sample.rollDegrees,
            pitchDegrees: sample.pitchDegrees,
          },
          pose: {
            yaw: state.pose.yaw + sample.yawRate * dtSeconds,
            pitch: state.pose.pitch + sample.pitchRate * dtSeconds,
          },
          hasGyro: state.hasGyro || sample.hasGyro,
          clockMs: atMs,
          motionMs: atMs,
        };
        const judged = judge(next, stepMs(state, atMs));
        // Holding steady while facing a direction counts towards coverage,
        // even when frames are thin. A swing or a pause does not.
        const steady =
          sample.hasGyro && judged.guardrails.motion === "good" && !judged.pause.paused;
        return steady
          ? { ...judged, coverage: addSweep(judged.coverage, judged.pose.yaw) }
          : judged;
      }
      case "frame": {
        const { stats, points, aspect, atMs } = event;
        const judged = judge(
          {
            ...state,
            frame: { stats, aspect, featureCount: points.length },
            clockMs: atMs,
          },
          stepMs(state, atMs),
        );
        // While paused or moving too fast the mesh is kept exactly as it was:
        // nothing is lost, and blurred frames add nothing.
        if (!shouldUseFrame(judged.pause, judged.guardrails)) return judged;

        // Turning left (positive yaw) moves the scene right on screen;
        // tilting up (positive pitch) moves it down.
        const fov = frameFov(aspect);
        const moved = shiftMesh(
          judged.mesh,
          wrapDegrees(judged.pose.yaw - judged.meshPose.yaw) / fov.across,
          (judged.pose.pitch - judged.meshPose.pitch) / fov.down,
        );
        return {
          ...judged,
          mesh: updateMesh(moved, points, tracker),
          meshPose: judged.pose,
          coverage: addFrame(judged.coverage, judged.pose.yaw, points.length),
          usableFrames: judged.usableFrames + 1,
        };
      }
    }
  };
}

/** Steady frames needed before Done, on top of coverage. */
export const MIN_USABLE_FRAMES = 15;

/** Enough has been mapped for "Done" to make sense. */
export function canFinish(state: ScanState): boolean {
  return enoughCoverage(state.coverage, state.hasGyro) && state.usableFrames >= MIN_USABLE_FRAMES;
}

/** 0 to 1, shown as the share mapped. */
export function mappedShare(state: ScanState): number {
  return coverageFraction(state.coverage, state.hasGyro);
}
