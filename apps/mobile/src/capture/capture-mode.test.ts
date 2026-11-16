import { AUTO_SIMPLE_AFTER_MS, initialMode, modeAfter, type ModeSignals } from "./capture-mode";

const working: ModeSignals = { planes: 3, meshTriangles: 0, detector: true, detectorFailed: false };

describe("capture mode", () => {
  it("starts simple on Android and never changes", () => {
    const android = initialMode("android");
    expect(android).toMatchObject({ mode: "simple", reason: "android", decided: true });
    expect(modeAfter(android, working, 60_000)).toBe(android);
  });

  it("starts full elsewhere and stays full when planes and the detector work", () => {
    let state = initialMode("ios");
    state = modeAfter(state, { ...working, planes: 0, detector: false }, 1_000);
    expect(state).toMatchObject({ mode: "full", decided: false, startedMs: 1_000 });
    state = modeAfter(state, working, 1_000 + AUTO_SIMPLE_AFTER_MS);
    expect(state).toMatchObject({ mode: "full", reason: null, decided: true });
  });

  it("turns simple when no planes are found in the first ten seconds", () => {
    let state = modeAfter(initialMode("ios"), { ...working, planes: 0 }, 0);
    state = modeAfter(state, { ...working, planes: 0 }, AUTO_SIMPLE_AFTER_MS - 1);
    expect(state.mode).toBe("full");
    state = modeAfter(state, { ...working, planes: 0 }, AUTO_SIMPLE_AFTER_MS);
    expect(state).toMatchObject({ mode: "simple", reason: "noPlanes", decided: true });
  });

  it("counts a LiDAR mesh as surfaces found", () => {
    let state = modeAfter(initialMode("ios"), working, 0);
    state = modeAfter(state, { ...working, planes: 0, meshTriangles: 900 }, AUTO_SIMPLE_AFTER_MS);
    expect(state.mode).toBe("full");
  });

  it("turns simple at once when the detector fails to load, and at ten seconds when it never loads", () => {
    const failed = modeAfter(initialMode("ios"), { ...working, detectorFailed: true }, 500);
    expect(failed).toMatchObject({ mode: "simple", reason: "detector", decided: true });
    let loading = modeAfter(initialMode("ios"), { ...working, detector: false }, 0);
    loading = modeAfter(loading, { ...working, detector: false }, AUTO_SIMPLE_AFTER_MS);
    expect(loading).toMatchObject({ mode: "simple", reason: "detector" });
  });

  it("never switches back once simple", () => {
    let state = modeAfter(initialMode("ios"), { ...working, planes: 0 }, 0);
    state = modeAfter(state, { ...working, planes: 0 }, AUTO_SIMPLE_AFTER_MS);
    expect(modeAfter(state, working, 60_000).mode).toBe("simple");
  });
});
