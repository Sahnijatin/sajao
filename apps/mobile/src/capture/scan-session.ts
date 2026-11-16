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
import { type DoorwayState, NO_DOORWAY, type Point2, updateDoorway } from "./ar/guidance";
import {
  addSurfaceSample,
  CELL_M,
  EMPTY_SURFACE_COVERAGE,
  type SurfaceCoverage,
  surfaceFraction,
  type SurfaceHit,
} from "./ar/surface-coverage";
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

/** AR tracking quality as the native session reports it. */
export type ArTracking = "none" | "initializing" | "normal" | "limited" | "notAvailable";

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
  /**
   * Where the pose comes from: the gyroscope (integrated, drifts slowly) or
   * AR world tracking (anchored to the room, no drift). AR wins once it reports.
   */
  poseSource: "gyro" | "ar";
  /** AR tracking quality; "none" when there is no AR session. */
  tracking: ArTracking;
  /** Time of the last event and of the last motion reading, in ms. */
  clockMs: number | null;
  motionMs: number | null;
  /** Frames that were good enough to use, so far. */
  usableFrames: number;
  /**
   * AR scan coverage on walls and floor. Used once the AR view sends its
   * first surface sample; until then (or on an older build) coverage is by
   * direction.
   */
  surfaces: SurfaceCoverage;
  surfacesSeen: boolean;
  /** How fast the AR camera turns, degrees per second, from AR poses. */
  turnRate: number;
  /** The previous AR pose, to measure the turn. */
  lastArPose: { yaw: number; pitch: number; atMs: number } | null;
  /** Camera position on the floor plan, from AR tracking; null without AR. */
  position: Point2 | null;
  /**
   * Which side of the mapped walls the camera is on. One space per scan:
   * beyond a wall (through a doorway) nothing counts until you come back.
   */
  doorway: DoorwayState;
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
  poseSource: "gyro",
  tracking: "none",
  clockMs: null,
  motionMs: null,
  usableFrames: 0,
  surfaces: EMPTY_SURFACE_COVERAGE,
  surfacesSeen: false,
  turnRate: 0,
  lastArPose: null,
  position: null,
  doorway: NO_DOORWAY,
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
  | {
      /** Camera direction from AR world tracking, gravity aligned, in degrees. */
      type: "arPose";
      yaw: number;
      pitch: number;
      tracking: ArTracking;
      /** Camera position on the floor plan, metres; null from older builds. */
      position?: Point2 | null;
      atMs: number;
    }
  | {
      /** One AR camera frame's measurements, a few times a second. */
      type: "arFrame";
      /** Mean brightness of the camera image, 0 to 255. */
      brightness: number;
      /** The AR light estimate says the room is dim even if the picture looks bright. */
      lowLight: boolean;
      /** Feature points the tracker sees in this frame. */
      featureCount: number;
      tracking: ArTracking;
      atMs: number;
    }
  | {
      /** Where a small grid of rays from the AR camera landed on walls and floor. */
      type: "arSurfaces";
      sharpness: number;
      hits: readonly SurfaceHit[];
      floorY?: number | null;
      atMs: number;
    }
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
        const arPose = state.poseSource === "ar";
        const next: ScanState = {
          ...state,
          motion: {
            rotationRate: smooth(state.motion.rotationRate, sample.rotationRate),
            acceleration: smooth(state.motion.acceleration, sample.acceleration),
            rollDegrees: sample.rollDegrees,
            pitchDegrees: sample.pitchDegrees,
          },
          // With AR tracking the pose comes from the AR session instead.
          pose: arPose
            ? state.pose
            : {
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
          !arPose && sample.hasGyro && judged.guardrails.motion === "good" && !judged.pause.paused;
        return steady
          ? { ...judged, coverage: addSweep(judged.coverage, judged.pose.yaw) }
          : judged;
      }
      case "arPose": {
        const judged = judge(
          {
            ...state,
            pose: { yaw: event.yaw, pitch: event.pitch },
            meshPose: { yaw: event.yaw, pitch: event.pitch },
            poseSource: "ar",
            tracking: event.tracking,
            hasGyro: true,
            clockMs: event.atMs,
            turnRate: turnRateAfter(state, event),
            lastArPose: { yaw: event.yaw, pitch: event.pitch, atMs: event.atMs },
            position: event.position ?? state.position,
            doorway:
              event.position && event.tracking === "normal"
                ? updateDoorway(state.doorway, state.surfaces.walls, event.position, CELL_M)
                : state.doorway,
          },
          stepMs(state, event.atMs),
        );
        // Facing a direction earns nothing by itself; coverage comes from
        // sharp, slow frames that land on walls and floor (arSurfaces). Older
        // builds without surface samples still count steady directions.
        const steady =
          !state.surfacesSeen &&
          event.tracking === "normal" &&
          judged.guardrails.motion === "good" &&
          !judged.pause.paused;
        return steady ? { ...judged, coverage: addSweep(judged.coverage, event.yaw) } : judged;
      }
      case "arSurfaces": {
        // Nothing counts while paused or beyond a doorway; what was mapped stays.
        if (state.pause.paused || state.doorway.outside) return { ...state, surfacesSeen: true };
        const sample = { sharpness: event.sharpness, hits: event.hits, floorY: event.floorY };
        const surfaces = addSurfaceSample(
          state.surfaces,
          sample,
          state.turnRate,
          state.tracking === "normal",
        );
        const accepted = surfaces.accepted > state.surfaces.accepted;
        return {
          ...state,
          surfaces,
          surfacesSeen: true,
          // The mini-map shows the directions of accepted samples only.
          coverage: accepted
            ? addFrame(state.coverage, state.pose.yaw, state.frame?.featureCount ?? 0)
            : state.coverage,
          usableFrames: state.usableFrames + (accepted ? 1 : 0),
        };
      }
      case "arFrame": {
        const stats = { brightness: event.brightness, glare: 0, sharpness: 0 };
        const judged = judge(
          {
            ...state,
            frame: {
              stats,
              aspect: state.frame?.aspect ?? 9 / 16,
              featureCount: event.featureCount,
            },
            isoRatio: event.lowLight ? 1 : 0,
            tracking: event.tracking,
            clockMs: event.atMs,
          },
          stepMs(state, event.atMs),
        );
        if (
          state.surfacesSeen ||
          event.tracking !== "normal" ||
          !shouldUseFrame(judged.pause, judged.guardrails)
        ) {
          return judged;
        }
        return {
          ...judged,
          coverage: addFrame(judged.coverage, judged.pose.yaw, event.featureCount),
          usableFrames: judged.usableFrames + 1,
        };
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

/** Weight of a new turn reading against the running value. */
const TURN_SMOOTHING = 0.5;

/** Turn rate after a new AR pose: the angle between poses over the time between them. */
function turnRateAfter(state: ScanState, pose: { yaw: number; pitch: number; atMs: number }) {
  const last = state.lastArPose;
  if (!last) return 0;
  const dtSeconds = (pose.atMs - last.atMs) / 1000;
  // A long gap (app in background) says nothing about turning.
  if (dtSeconds <= 0 || dtSeconds > 1) return state.turnRate;
  const turned = Math.hypot(wrapDegrees(pose.yaw - last.yaw), pose.pitch - last.pitch);
  return state.turnRate + (turned / dtSeconds - state.turnRate) * TURN_SMOOTHING;
}

/** Steady frames needed before Done, on top of coverage. */
export const MIN_USABLE_FRAMES = 15;
/** Done is offered at this share of walls and floor: a corner, two walls and some floor. */
export const SURFACE_DONE_SHARE = 0.45;

/** Enough has been mapped for "Done" to make sense. */
export function canFinish(state: ScanState): boolean {
  const covered = state.surfacesSeen
    ? surfaceFraction(state.surfaces) >= SURFACE_DONE_SHARE
    : enoughCoverage(state.coverage, state.hasGyro);
  return covered && state.usableFrames >= MIN_USABLE_FRAMES;
}

/** 0 to 1, shown as the share mapped. */
export function mappedShare(state: ScanState): number {
  return state.surfacesSeen
    ? surfaceFraction(state.surfaces)
    : coverageFraction(state.coverage, state.hasGyro);
}
