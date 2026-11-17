// Frame rates for the debug overlay during the AR scan. ARKit and ARCore own
// the camera then, so the 2D frame callback never runs; the native view counts
// its own camera frames and detector runs instead, as running totals.

export interface ArFrameCounters {
  /** AR camera frames seen since the view started. */
  frames: number;
  /** Detector runs finished. */
  detectorRuns: number;
  /** Frames the pacer wanted to send while the detector was still busy. */
  detectorSkipped: number;
  /** How long the latest detector run took. */
  detectorMs: number;
}

export interface ArFrameRates {
  cameraFps: number;
  detectorFps: number;
  detectorMs: number;
  detectorSkipped: number;
}

export const NO_AR_COUNTERS: ArFrameCounters = {
  frames: 0,
  detectorRuns: 0,
  detectorSkipped: 0,
  detectorMs: 0,
};

/** Reads the counters from a native status event; older builds send none. */
export function arCountersOf(status: Partial<Record<keyof ArFrameCounters, unknown>>) {
  const read = (value: unknown) =>
    typeof value === "number" && Number.isFinite(value) ? Math.max(0, value) : 0;
  return {
    frames: read(status.frames),
    detectorRuns: read(status.detectorRuns),
    detectorSkipped: read(status.detectorSkipped),
    detectorMs: read(status.detectorMs),
  };
}

/**
 * Rates over one debug window. A total that went down means the native view
 * restarted, so the window counts from zero.
 */
export function arFrameRates(
  previous: ArFrameCounters,
  current: ArFrameCounters,
  seconds: number,
): ArFrameRates {
  const span = Math.max(0.001, seconds);
  const delta = (now: number, before: number) => (now >= before ? now - before : now);
  return {
    cameraFps: Math.round(delta(current.frames, previous.frames) / span),
    detectorFps: Math.round(delta(current.detectorRuns, previous.detectorRuns) / span),
    detectorMs: Math.round(current.detectorMs),
    detectorSkipped: delta(current.detectorSkipped, previous.detectorSkipped),
  };
}
