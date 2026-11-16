// The whole state of a scan, advanced by events: an analysed frame, a
// motion sensor reading, or the user choosing to scan anyway. Pure, so the
// behaviour of the capture screen is tested without a camera.
import type { FeaturePoint } from "./feature-points";
import type { FrameStats } from "./frame-stats";
import {
  ALL_GOOD,
  evaluateGuardrails,
  type GuardrailState,
  NOT_PAUSED,
  type PauseState,
  scanAnyway,
  shouldUseFrame,
  updatePause,
} from "./guardrails";
import {
  DEFAULT_TRACKER_OPTIONS,
  EMPTY_MESH,
  LOW_TIER_TRACKER_OPTIONS,
  type MeshState,
  updateMesh,
} from "./mesh-tracker";

export interface ScanState {
  mesh: MeshState;
  guardrails: GuardrailState;
  pause: PauseState;
  motion: { rotationRate: number; rollDegrees: number };
  /** Frames that were good enough to use, so far. */
  usableFrames: number;
}

export const INITIAL_SCAN: ScanState = {
  mesh: EMPTY_MESH,
  guardrails: ALL_GOOD,
  pause: NOT_PAUSED,
  motion: { rotationRate: 0, rollDegrees: 0 },
  usableFrames: 0,
};

export type ScanEvent =
  | { type: "frame"; stats: FrameStats; points: FeaturePoint[]; elapsedMs: number }
  | { type: "motion"; rotationRate: number; rollDegrees: number }
  | { type: "scanAnyway" }
  | { type: "reset" };

export function scanReducer(tier: "standard" | "low") {
  const tracker = tier === "low" ? LOW_TIER_TRACKER_OPTIONS : DEFAULT_TRACKER_OPTIONS;
  return (state: ScanState, event: ScanEvent): ScanState => {
    switch (event.type) {
      case "reset":
        return INITIAL_SCAN;
      case "motion":
        return {
          ...state,
          motion: { rotationRate: event.rotationRate, rollDegrees: event.rollDegrees },
        };
      case "scanAnyway":
        return { ...state, pause: scanAnyway(state.pause) };
      case "frame": {
        const guardrails = evaluateGuardrails(state.guardrails, {
          ...event.stats,
          ...state.motion,
        });
        const pause = updatePause(state.pause, guardrails, event.elapsedMs);
        // While paused or moving too fast the mesh is kept exactly as it was:
        // nothing is lost, and blurred frames add nothing.
        if (!shouldUseFrame(pause, guardrails)) return { ...state, guardrails, pause };
        return {
          ...state,
          guardrails,
          pause,
          mesh: updateMesh(state.mesh, event.points, tracker),
          usableFrames: state.usableFrames + 1,
        };
      }
    }
  };
}

/** Enough has been mapped for "Done" to make sense. */
export const MIN_COVERAGE_TO_FINISH = 0.25;

export function canFinish(state: ScanState): boolean {
  return state.mesh.coverage >= MIN_COVERAGE_TO_FINISH && state.usableFrames >= 10;
}

/** Sideways tilt in degrees from a gravity vector (device held upright in portrait). */
export function rollFromGravity(gravity: { x: number; y: number }): number {
  return (Math.atan2(gravity.x, -gravity.y) * 180) / Math.PI;
}

/** Turn rate in degrees per second from gyroscope axes in radians per second. */
export function rotationRateDegrees(rate: { x: number; y: number; z: number }): number {
  return (Math.hypot(rate.x, rate.y, rate.z) * 180) / Math.PI;
}
