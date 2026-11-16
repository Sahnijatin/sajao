import { arCountersOf, arFrameRates, NO_AR_COUNTERS } from "./ar-debug";

describe("AR frame rates", () => {
  it("turns running totals into per-second rates over the window", () => {
    const before = { frames: 600, detectorRuns: 80, detectorSkipped: 3, detectorMs: 30 };
    const after = { frames: 660, detectorRuns: 88, detectorSkipped: 4, detectorMs: 41.6 };
    expect(arFrameRates(before, after, 1)).toEqual({
      cameraFps: 60,
      detectorFps: 8,
      detectorMs: 42,
      detectorSkipped: 1,
    });
  });

  it("counts from zero when the native view restarts", () => {
    const before = { frames: 900, detectorRuns: 120, detectorSkipped: 9, detectorMs: 30 };
    const after = { frames: 30, detectorRuns: 4, detectorSkipped: 0, detectorMs: 30 };
    expect(arFrameRates(before, after, 0.5)).toMatchObject({ cameraFps: 60, detectorFps: 8 });
  });

  it("reads counters defensively from older builds", () => {
    expect(arCountersOf({})).toEqual(NO_AR_COUNTERS);
    expect(arCountersOf({ frames: Number.NaN, detectorRuns: -3, detectorMs: 12 })).toEqual({
      ...NO_AR_COUNTERS,
      detectorMs: 12,
    });
  });
});
