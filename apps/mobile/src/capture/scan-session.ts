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
  MAX_TURN_DEG_PER_S,
  pushRecent,
  type RejectCause,
  sharpEnough,
  shouldSlowDown,
  tooManyRejected,
  type SurfaceCoverage,
  surfaceFraction,
  type SurfaceHit,
} from "./ar/surface-coverage";
import { initialMode, modeAfter, type ModeSignals, type ModeState } from "./capture-mode";
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
import {
  addMeterSample,
  canFinishAnyway,
  EMPTY_METER,
  meterDone,
  meterFraction,
  type MeterState,
} from "./coverage-meter";
import {
  addMotionSample,
  EMPTY_MOTION_COVERAGE,
  type MotionCoverage,
  MAX_PITCH_DEGREES,
  motionDone,
  motionFraction,
  rejectMotionSample,
} from "./motion-coverage";
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
  /** Recent frame sharpness, to judge blur on this phone and in this light. */
  frameSharpness: readonly number[];
  /** 2D scan: why recent frames did not count (null when they did), newest last. */
  recentFrames: readonly (RejectCause | null)[];
  /** Full or simple scan, and why. */
  mode: ModeState;
  /**
   * Coverage from how the camera turned and moved. Counted in both modes,
   * so a scan that turns simple at ten seconds keeps what it earned.
   */
  motionCoverage: MotionCoverage;
  /**
   * The coverage meter: the loop round the space and the sweeps from inside
   * it, from AR positions. It gates Done on every phone whose AR tracks.
   */
  meter: MeterState;
  /** Whether the latest AR camera frame was sharp, and when it was judged. */
  sharp: { ok: boolean; atMs: number } | null;
  /** Since when AR tracking has seen too little to track well; null while it sees enough. */
  lowDetailSinceMs: number | null;
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
  frameSharpness: [],
  recentFrames: [],
  mode: initialMode("ios"),
  motionCoverage: EMPTY_MOTION_COVERAGE,
  meter: EMPTY_METER,
  sharp: null,
  lowDetailSinceMs: null,
};

/** The starting state on a platform: Android starts in the simple scan. */
export function initialScan(platform: "ios" | "android" | "none"): ScanState {
  return { ...INITIAL_SCAN, mode: initialMode(platform) };
}

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
      /** Planes and detector state, to decide between the full and the simple scan. */
      signals?: ModeSignals;
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
        // Android stays in the simple scan after a reset.
        return {
          ...INITIAL_SCAN,
          mode: state.mode.reason === "android" ? state.mode : INITIAL_SCAN.mode,
        };
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
        // AR drives the pose only while it tracks; when tracking is lost the
        // gyroscope carries the heading on from the last AR pose.
        const arPose = state.poseSource === "ar" && state.tracking === "normal";
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
        // Facing a direction earns nothing by itself: coverage comes from
        // sharp frames taken while turning slowly (the "frame" event).
        const judged = judge(next, stepMs(state, atMs));
        // An AR scan whose tracking is lost still counts motion coverage, from the gyroscope.
        if (state.poseSource !== "ar" || state.tracking === "normal" || !sample.hasGyro) {
          return judged;
        }
        return {
          ...judged,
          motionCoverage: addMotionSample(judged.motionCoverage, {
            yaw: judged.pose.yaw,
            pitch: judged.pose.pitch,
            turnDegPerS: judged.motion.rotationRate,
            steady: judged.guardrails.motion === "good" && !judged.pause.paused,
            sharp: sharpNow(judged, atMs),
            position: null,
            atMs,
          }),
        };
      }
      case "arPose": {
        const tracked = event.tracking === "normal";
        if (!tracked) {
          // A pose from a session that is not tracking is stale: the
          // gyroscope carries the heading until tracking returns.
          return judge(
            {
              ...state,
              poseSource: "ar",
              tracking: event.tracking,
              hasGyro: true,
              clockMs: event.atMs,
              lastArPose: null,
            },
            stepMs(state, event.atMs),
          );
        }
        const turnRate = turnRateAfter(state, event);
        const judged = judge(
          {
            ...state,
            pose: { yaw: event.yaw, pitch: event.pitch },
            meshPose: { yaw: event.yaw, pitch: event.pitch },
            poseSource: "ar",
            tracking: event.tracking,
            hasGyro: true,
            clockMs: event.atMs,
            turnRate,
            lastArPose: { yaw: event.yaw, pitch: event.pitch, atMs: event.atMs },
            position: event.position ?? state.position,
            doorway: event.position
              ? updateDoorway(state.doorway, state.surfaces.walls, event.position, CELL_M)
              : state.doorway,
          },
          stepMs(state, event.atMs),
        );
        const still = judged.guardrails.motion === "good" && !judged.pause.paused;
        const motion = {
          yaw: event.yaw,
          pitch: event.pitch,
          turnDegPerS: turnRate,
          steady: still,
          sharp: sharpNow(judged, event.atMs),
          position: event.position ?? null,
          atMs: event.atMs,
        };
        // The meter takes a pose under the same gates as motion coverage:
        // slow, steady, sharp, and within 60 degrees of level.
        const counts =
          event.position != null &&
          rejectMotionSample(motion) === null &&
          Math.abs(event.pitch) <= MAX_PITCH_DEGREES;
        const withMotion: ScanState = {
          ...judged,
          motionCoverage: addMotionSample(judged.motionCoverage, motion),
          meter:
            counts && event.position
              ? addMeterSample(judged.meter, {
                  position: event.position,
                  yaw: event.yaw,
                  pitch: event.pitch,
                  atMs: event.atMs,
                })
              : judged.meter,
        };
        // Facing a direction earns nothing by itself; coverage comes from
        // sharp, slow frames that land on walls and floor (arSurfaces). Older
        // builds without surface samples still count steady directions.
        const steady = !state.surfacesSeen && still;
        return steady
          ? { ...withMotion, coverage: addSweep(withMotion.coverage, event.yaw) }
          : withMotion;
      }
      case "arSurfaces": {
        // Every sample says how sharp the camera frame is, in both modes.
        const judgedSharp: ScanState = Number.isFinite(event.sharpness)
          ? {
              ...state,
              sharp: {
                ok: sharpEnough(state.frameSharpness, event.sharpness),
                atMs: event.atMs,
              },
              frameSharpness: [...state.frameSharpness, event.sharpness].slice(-40),
            }
          : state;
        // The simple scan counts nothing from surfaces.
        if (state.mode.mode === "simple") return judgedSharp;
        state = judgedSharp;
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
            mode: event.signals ? modeAfter(state.mode, event.signals, event.atMs) : state.mode,
            lowDetailSinceMs: lowDetail(event.tracking, event.featureCount)
              ? (state.lowDetailSinceMs ?? event.atMs)
              : null,
          },
          stepMs(state, event.atMs),
        );
        if (
          judged.mode.mode === "simple" ||
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
        // Coverage counts only a frame taken turning slowly that is sharp
        // against this scan's recent frames: a fast pan or a blurred frame
        // earns nothing, and asks you to slow down.
        const cause: RejectCause | null =
          judged.motion.rotationRate > MAX_TURN_DEG_PER_S
            ? "turning"
            : !sharpEnough(judged.frameSharpness, stats.sharpness)
              ? "blurred"
              : null;
        return {
          ...judged,
          mesh: updateMesh(moved, points, tracker),
          meshPose: judged.pose,
          coverage:
            cause === null
              ? addFrame(judged.coverage, judged.pose.yaw, points.length)
              : judged.coverage,
          usableFrames: judged.usableFrames + (cause === null ? 1 : 0),
          frameSharpness: [...judged.frameSharpness, stats.sharpness].slice(-40),
          recentFrames: pushRecent(judged.recentFrames, cause),
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
/** Done is offered at this share of walls and floor; "cover a bit more" shows until 100%. */
export const SURFACE_DONE_SHARE = 0.7;

/** Enough has been mapped for "Done" to make sense. */
export function canFinish(state: ScanState): boolean {
  if (isMeter(state)) return meterDone(state.meter);
  if (isSimple(state)) return motionDone(state.motionCoverage);
  const covered = state.surfacesSeen
    ? surfaceFraction(state.surfaces) >= SURFACE_DONE_SHARE
    : enoughCoverage(state.coverage, state.hasGyro);
  return covered && state.usableFrames >= MIN_USABLE_FRAMES;
}

/** Recent samples (AR) or frames (2D) were rejected for turning fast or blur. */
export function shouldShowSlowDown(state: ScanState): boolean {
  if (isMeter(state)) return tooManyRejected(state.motionCoverage.recent);
  if (isSimple(state)) return tooManyRejected(state.motionCoverage.recent);
  return state.surfacesSeen ? shouldSlowDown(state.surfaces) : tooManyRejected(state.recentFrames);
}

/** 0 to 1, shown as the share mapped. */
export function mappedShare(state: ScanState): number {
  if (isMeter(state)) return meterFraction(state.meter);
  if (isSimple(state)) return motionFraction(state.motionCoverage);
  return state.surfacesSeen
    ? surfaceFraction(state.surfaces)
    : coverageFraction(state.coverage, state.hasGyro);
}

/** The scan counts coverage from camera motion, not from planes or the detector. */
export function isSimple(state: ScanState): boolean {
  return state.mode.mode === "simple" && state.poseSource === "ar";
}

/** A sharpness verdict older than this says nothing about the frame now. */
const SHARP_FRESH_MS = 1000;

/** Whether the camera frame is sharp now; true when there is no recent verdict. */
function sharpNow(state: ScanState, atMs: number): boolean {
  return !state.sharp || atMs - state.sharp.atMs > SHARP_FRESH_MS ? true : state.sharp.ok;
}

/** AR tracking with fewer feature points than this is looking at too little: a blank wall, close up. */
export const MIN_TRACKED_FEATURES = 15;
/** Too little detail for this long asks the person to step back. */
export const STEP_BACK_AFTER_MS = 1500;

function lowDetail(tracking: ArTracking, featureCount: number): boolean {
  return tracking === "limited" || (tracking === "normal" && featureCount < MIN_TRACKED_FEATURES);
}

/** AR tracking has seen too little for a while in good light: step back to show it more. */
export function shouldStepBack(state: ScanState): boolean {
  return (
    state.lowDetailSinceMs !== null &&
    state.clockMs !== null &&
    state.clockMs - state.lowDetailSinceMs >= STEP_BACK_AFTER_MS &&
    state.guardrails.light === "good"
  );
}

/**
 * The coverage meter decides Done: AR is tracking and has given positions.
 * A phone whose AR never tracks has no positions, and keeps the simple
 * scan's heading and steady-time rule.
 */
export function isMeter(state: ScanState): boolean {
  return state.poseSource === "ar" && state.meter.samples > 0;
}

/** Coverage has not moved for a minute: the person may finish with what there is. */
export function canFinishEarly(state: ScanState): boolean {
  return isMeter(state) && state.clockMs !== null && canFinishAnyway(state.meter, state.clockMs);
}
