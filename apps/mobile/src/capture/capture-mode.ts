// Which scan a phone gets. The full scan counts coverage on walls and floor
// from AR planes and offers hints from live labels. The simple scan asks
// nothing of planes or the detector: it records the same capture package
// (video, AR poses, motion sensors, keyframes) and counts coverage from how
// the camera turned and moved. The live mesh and labels still draw wherever
// the phone finds them; they are a preview, never a requirement.
//
// Android starts simple. Any phone falls back to simple when planes or the
// detector have not worked ten seconds into the scan. Simple never switches
// back, so progress never jumps mid-scan.

export type CaptureMode = "full" | "simple";
/** Why the scan is simple; null in the full scan. */
export type SimpleReason = "android" | "noPlanes" | "detector" | null;

/** Planes and the detector get this long to work before the scan turns simple. */
export const AUTO_SIMPLE_AFTER_MS = 10_000;

export interface ModeState {
  mode: CaptureMode;
  reason: SimpleReason;
  /** When the AR session first reported, in ms; null before it has. */
  startedMs: number | null;
  /** The ten-second check has run: the mode is final. */
  decided: boolean;
}

export function initialMode(platform: "ios" | "android" | "none"): ModeState {
  return platform === "android"
    ? { mode: "simple", reason: "android", startedMs: null, decided: true }
    : { mode: "full", reason: null, startedMs: null, decided: false };
}

/** What the AR session reports about the two things the full scan needs. */
export interface ModeSignals {
  /** Planes found so far. */
  planes: number;
  /** LiDAR scene mesh triangles; a LiDAR phone maps surfaces without planes. */
  meshTriangles: number;
  /** The detector loaded and passed its self-test. */
  detector: boolean;
  /** The detector reported a load error. */
  detectorFailed: boolean;
}

/** The mode after one AR status report. Pure. */
export function modeAfter(state: ModeState, signals: ModeSignals, atMs: number): ModeState {
  if (state.decided) return state;
  const startedMs = state.startedMs ?? atMs;
  // A detector that failed to load will not recover: no need to wait.
  if (signals.detectorFailed) {
    return { mode: "simple", reason: "detector", startedMs, decided: true };
  }
  if (atMs - startedMs < AUTO_SIMPLE_AFTER_MS) return { ...state, startedMs };
  if (signals.planes <= 0 && signals.meshTriangles <= 0) {
    return { mode: "simple", reason: "noPlanes", startedMs, decided: true };
  }
  if (!signals.detector) return { mode: "simple", reason: "detector", startedMs, decided: true };
  return { ...state, startedMs, decided: true };
}
